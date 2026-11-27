variable "project_name" {
  type = string
}

variable "runtime_enabled" {
  description = "Creates the ALB and the ECS services, which bill by the hour."
  type        = bool
}

variable "image_tag" {
  description = "Git SHA of the image the deploy pushed; the base task definitions point at it."
  type        = string
}

variable "iam_path" {
  type = string
}

variable "permissions_boundary_arn" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "database_url" {
  description = "DATABASE_URL without a password; null while the environment is stopped."
  type        = string
  default     = null
}

variable "database_password_secret_arn" {
  type = string
}

variable "database_security_group_id" {
  type = string
}

variable "user_pool_arn" {
  type = string
}

variable "shared_environment" {
  description = "Environment variables of every task (the API's Settings)."
  type        = map(string)
}

variable "extraction_environment" {
  type = map(string)
}

variable "review_environment" {
  type = map(string)
}

variable "api_policy_arns" {
  description = "Static keys: the ARNs of policies created in the same apply are unknown at plan."
  type        = map(string)
}

variable "extraction_policy_arns" {
  description = "Static keys: the ARNs of policies created in the same apply are unknown at plan."
  type        = map(string)
}

variable "review_policy_arns" {
  description = "Static keys: the ARNs of policies created in the same apply are unknown at plan."
  type        = map(string)
}
