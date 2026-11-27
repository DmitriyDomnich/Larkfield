variable "project_name" {
  type = string
}

variable "user_pool_arn" {
  type = string
}

variable "iam_path" {
  description = "IAM path of the module's roles and policies; the deploy role manages only this path."
  type        = string
  default     = "/"
}

variable "permissions_boundary_arn" {
  description = "Boundary every role must carry for the deploy role to create it."
  type        = string
  default     = null
}
