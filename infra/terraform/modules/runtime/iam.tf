data "aws_iam_policy_document" "ecs_tasks_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ECS itself: pull the image, write logs, inject PGPASSWORD
resource "aws_iam_role" "execution" {
  name                 = "${var.project_name}-task-execution"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secret" {
  name = "read-db-password"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = var.database_password_secret_arn
    }]
  })
}

resource "aws_iam_role" "api" {
  name                 = "${var.project_name}-api-task"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
}

resource "aws_iam_role_policy_attachment" "api" {
  for_each   = var.api_policy_arns
  role       = aws_iam_role.api.name
  policy_arn = each.value
}

# role changes from the users endpoints
resource "aws_iam_role_policy" "api_user_groups" {
  name = "manage-user-groups"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "cognito-idp:AdminAddUserToGroup",
        "cognito-idp:AdminRemoveUserFromGroup",
        "cognito-idp:AdminListGroupsForUser",
        "cognito-idp:AdminGetUser",
      ]
      Resource = var.user_pool_arn
    }]
  })
}

# ECS Exec: the session channel for the database tunnel
resource "aws_iam_role_policy" "api_ecs_exec" {
  name = "ecs-exec"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssmmessages:CreateControlChannel",
        "ssmmessages:CreateDataChannel",
        "ssmmessages:OpenControlChannel",
        "ssmmessages:OpenDataChannel",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role" "extraction_worker" {
  name                 = "${var.project_name}-extraction-task"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
}

resource "aws_iam_role_policy_attachment" "extraction_worker" {
  for_each   = var.extraction_policy_arns
  role       = aws_iam_role.extraction_worker.name
  policy_arn = each.value
}

resource "aws_iam_role" "review_worker" {
  name                 = "${var.project_name}-review-task"
  path                 = var.iam_path
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.ecs_tasks_trust.json
}

resource "aws_iam_role_policy_attachment" "review_worker" {
  for_each   = var.review_policy_arns
  role       = aws_iam_role.review_worker.name
  policy_arn = each.value
}
