variable "project_name" {
  type = string
}

variable "runtime_enabled" {
  description = "Creates the NAT gateway and its Elastic IP, which bill by the hour."
  type        = bool
}

variable "cidr_block" {
  type    = string
  default = "10.40.0.0/16"
}
