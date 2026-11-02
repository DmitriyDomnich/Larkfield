variable "project_name" {
  type = string
}

variable "frontend_origins" {
  description = "Origins allowed to upload to and view from the bucket (CORS)."
  type        = list(string)
}
