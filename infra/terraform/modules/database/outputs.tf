output "url_without_password" {
  description = "DATABASE_URL; libpq takes the password from PGPASSWORD."
  value = (
    var.runtime_enabled
    ? "postgresql://${var.username}@${aws_db_instance.main[0].address}:${aws_db_instance.main[0].port}/${var.database_name}"
    : null
  )
}

output "password_secret_arn" {
  value = aws_secretsmanager_secret.db.arn
}

output "security_group_id" {
  value = aws_security_group.db.id
}

output "latest_snapshot" {
  value = local.latest_snapshot
}
