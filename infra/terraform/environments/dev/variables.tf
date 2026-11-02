variable "aws_region" {
  type = string
}

variable "project_name" {
  type    = string
  default = "larkfield-dev"
}

variable "frontend_origins" {
  type    = list(string)
  default = ["http://localhost:3000"]
}
