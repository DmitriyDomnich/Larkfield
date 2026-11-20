variable "project_name" {
  type = string
}

variable "runtime_enabled" {
  description = "Adds the VPC origin and the /api/* behavior; while stopped the distribution serves the site only."
  type        = bool
}

variable "frontend_app_dir" {
  description = "frontend/src/app: its page.tsx files are the routes the site function maps to .html files."
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "load_balancer_arn" {
  type    = string
  default = null
}

variable "load_balancer_dns_name" {
  type    = string
  default = null
}

variable "load_balancer_security_group_id" {
  type = string
}
