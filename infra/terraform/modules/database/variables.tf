variable "project_name" {
  type = string
}

variable "runtime_enabled" {
  description = "Creates the RDS instance; Stop destroys it after a final snapshot."
  type        = bool
}

variable "restore_snapshot" {
  description = "Create the instance from the `<project>-latest` snapshot; the workflows set it when that snapshot exists."
  type        = bool
  default     = false
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "database_name" {
  type    = string
  default = "larkfield"
}

variable "username" {
  type    = string
  default = "larkfield"
}

variable "password_version" {
  description = "Bump to rotate the password: a new random value goes to the secret and the instance."
  type        = number
  default     = 1
}

variable "apply_password" {
  description = "false in the pull request plan, whose role can't read the secret; write-only values never show in a plan."
  type        = bool
  default     = true
}
