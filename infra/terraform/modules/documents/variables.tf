variable "project_name" {
  type = string
}

variable "frontend_origins" {
  description = "Origins allowed to upload to and view from the bucket (CORS)."
  type        = list(string)
}

variable "iam_path" {
  description = "IAM path of the module's roles and policies; the deploy role manages only this path."
  type        = string
  default     = "/"
}
