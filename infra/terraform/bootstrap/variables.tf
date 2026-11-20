variable "aws_region" {
  type = string
}

variable "project" {
  type    = string
  default = "larkfield"
}

variable "github_repo" {
  description = "owner/name of the repository whose workflows may assume the roles."
  type        = string
}

variable "environments" {
  description = "One deploy role and boundary per environment; each has a Terraform root."
  type        = list(string)
  default     = ["dev", "prod"]
}

variable "state_bucket" {
  description = "The existing Terraform state bucket (imported), as in backend.hcl."
  type        = string
}
