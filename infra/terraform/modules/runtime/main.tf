data "aws_region" "current" {}

locals {
  region = data.aws_region.current.region
  image  = "${aws_ecr_repository.app.repository_url}:${var.image_tag}"
  api_environment = merge(
    var.shared_environment,
    var.database_url == null ? {} : { DATABASE_URL = var.database_url },
  )
  tasks = {
    api = {
      cpu         = 512
      memory      = 1024
      command     = null
      environment = local.api_environment
      role_arn    = aws_iam_role.api.arn
    }
    extraction-worker = {
      cpu         = 256
      memory      = 512
      command     = ["python", "-m", "app.extraction"]
      environment = merge(local.api_environment, var.extraction_environment)
      role_arn    = aws_iam_role.extraction_worker.arn
    }
    review-worker = {
      cpu         = 512
      memory      = 1024
      command     = ["python", "-m", "app.review"]
      environment = merge(local.api_environment, var.review_environment)
      role_arn    = aws_iam_role.review_worker.arn
    }
    migrate = {
      cpu         = 256
      memory      = 512
      command     = ["alembic", "upgrade", "head"]
      environment = local.api_environment
      role_arn    = null
    }
  }
  services = toset(["api", "extraction-worker", "review-worker"])
}

resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the newest 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "main" {
  name = var.project_name
}

resource "aws_cloudwatch_log_group" "task" {
  for_each          = local.tasks
  name              = "/ecs/${var.project_name}/${each.key}"
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "task" {
  for_each                 = local.tasks
  family                   = "${var.project_name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = each.value.role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([merge(
    {
      name         = "app"
      image        = local.image
      essential    = true
      portMappings = each.key == "api" ? [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }] : []
      # workers finish the message in hand after SIGTERM
      stopTimeout = each.key == "api" ? 30 : 120
      environment = [for name in sort(keys(each.value.environment)) : { name = name, value = each.value.environment[name] }]
      secrets     = [{ name = "PGPASSWORD", valueFrom = var.database_password_secret_arn }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.task[each.key].name
          awslogs-region        = local.region
          awslogs-stream-prefix = each.key
        }
      }
    },
    each.value.command == null ? {} : { command = each.value.command },
  )])
}

resource "aws_ecs_service" "service" {
  for_each        = var.runtime_enabled ? local.services : toset([])
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.task[each.key].arn
  # no tasks until the deploy has run the migration; it then sets 1
  desired_count  = 0
  launch_type    = "FARGATE"
  propagate_tags = "SERVICE"
  # only the api, for the database tunnel
  enable_execute_command = each.key == "api"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [each.key == "api" ? aws_security_group.api.id : aws_security_group.workers.id]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  health_check_grace_period_seconds = each.key == "api" ? 60 : null

  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "app"
      container_port   = 8000
    }
  }

  lifecycle {
    # the deploy workflow rolls out new revisions; Terraform only creates the service
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.api]
}
