variable "project_name" {
  type = string
}

variable "environment" {
  description = "The metrics namespace is Larkfield/<environment> (the tasks' APP_ENV)."
  type        = string
}

variable "aws_region" {
  type = string
}

variable "runtime_enabled" {
  description = "Creates the alarms; a stopped environment never alarms."
  type        = bool
}

variable "alarm_email" {
  type = string
}

variable "dead_letter_queues" {
  description = "Alarm name part => DLQ name."
  type        = map(string)
}
