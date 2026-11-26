variable "project_name" {
  type = string
}

variable "agent_runtime_arn" {
  description = "The AgentCore runtime the review worker invokes (REVIEW_AGENT_RUNTIME_ARN)."
  type        = string
}

variable "max_receives" {
  description = "Deliveries of one request before it moves to the dead-letter queue (REVIEW_MAX_RECEIVES)."
  type        = number
  default     = 3
}

variable "iam_path" {
  description = "IAM path of the module's roles and policies; the deploy role manages only this path."
  type        = string
  default     = "/"
}
