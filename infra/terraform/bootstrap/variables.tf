variable "aws_region" {
  type = string
}

variable "project" {
  type    = string
  default = "larkfield"
}

variable "github_subject_prefix" {
  description = "The repository's OIDC subject prefix, e.g. repo:<owner>@<owner id>/<repo>@<repo id> with immutable subjects: gh api repos/<owner>/<repo>/actions/oidc/customization/sub (sub_claim_prefix)."
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
