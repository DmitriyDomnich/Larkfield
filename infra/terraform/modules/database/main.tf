terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}

# the secret is the password's source of truth; it outlives the instance across stop/start, so a
# restored snapshot still matches it. Write-only: the value is in neither the state nor the plan.
resource "aws_secretsmanager_secret" "db" {
  name                    = "${var.project_name}-db-password"
  recovery_window_in_days = 0
}

ephemeral "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id                = aws_secretsmanager_secret.db.id
  secret_string_wo         = ephemeral.random_password.db.result
  secret_string_wo_version = var.password_version
}

ephemeral "aws_secretsmanager_secret_version" "db" {
  count      = var.runtime_enabled && var.apply_password ? 1 : 0
  secret_id  = aws_secretsmanager_secret.db.id
  version_id = aws_secretsmanager_secret_version.db.version_id
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  name        = "${var.project_name}-db"
  description = "PostgreSQL, reachable from the ECS tasks only"
  vpc_id      = var.vpc_id
}

resource "aws_db_instance" "main" {
  count = var.runtime_enabled ? 1 : 0

  identifier          = "${var.project_name}-db"
  engine              = "postgres"
  engine_version      = "17"
  instance_class      = "db.t4g.micro"
  allocated_storage   = 20
  storage_type        = "gp3"
  storage_encrypted   = true
  multi_az            = false
  publicly_accessible = false

  db_name             = var.database_name
  username            = var.username
  password_wo         = one(ephemeral.aws_secretsmanager_secret_version.db[*].secret_string)
  password_wo_version = var.password_version

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]

  backup_retention_period    = 1
  delete_automated_backups   = true
  copy_tags_to_snapshot      = true
  skip_final_snapshot        = false
  final_snapshot_identifier  = local.latest_snapshot
  snapshot_identifier        = var.restore_snapshot ? local.latest_snapshot : null
  auto_minor_version_upgrade = true
  apply_immediately          = true
  deletion_protection        = false

  lifecycle {
    # only read on create: Start restores from the snapshot Stop took
    ignore_changes = [snapshot_identifier]
  }
}

locals {
  latest_snapshot = "${var.project_name}-latest"
}
