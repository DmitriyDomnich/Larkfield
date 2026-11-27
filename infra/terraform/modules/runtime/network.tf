resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb"
  description = "Internal ALB, reached only by the CloudFront VPC origin"
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "api" {
  name        = "${var.project_name}-api"
  description = "API tasks, reachable from the ALB only"
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "workers" {
  name        = "${var.project_name}-workers"
  description = "Worker and migration tasks, no inbound traffic"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "alb_to_api" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "api_from_alb" {
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "tasks_outbound" {
  for_each = {
    api     = aws_security_group.api.id
    workers = aws_security_group.workers.id
  }
  security_group_id = each.value
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "db_from_tasks" {
  for_each = {
    api     = aws_security_group.api.id
    workers = aws_security_group.workers.id
  }
  security_group_id            = var.database_security_group_id
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_lb" "api" {
  count              = var.runtime_enabled ? 1 : 0
  name               = "${var.project_name}-api"
  internal           = true
  load_balancer_type = "application"
  subnets            = var.private_subnet_ids
  security_groups    = [aws_security_group.alb.id]
}

resource "aws_lb_target_group" "api" {
  name                 = "${var.project_name}-api"
  vpc_id               = var.vpc_id
  target_type          = "ip"
  protocol             = "HTTP"
  port                 = 8000
  deregistration_delay = 30

  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_listener" "api" {
  count             = var.runtime_enabled ? 1 : 0
  load_balancer_arn = aws_lb.api[0].arn
  protocol          = "HTTP"
  port              = 80

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
