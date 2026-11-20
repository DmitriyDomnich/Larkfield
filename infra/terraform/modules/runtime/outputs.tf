output "repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_names" {
  value = sort(local.services)
}

output "task_families" {
  value = { for name, task in aws_ecs_task_definition.task : name => task.family }
}

output "migration_subnet_ids" {
  value = var.private_subnet_ids
}

output "migration_security_group_id" {
  value = aws_security_group.workers.id
}

output "load_balancer_arn" {
  value = one(aws_lb.api[*].arn)
}

output "load_balancer_security_group_id" {
  value = aws_security_group.alb.id
}
