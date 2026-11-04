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

variable "bedrock_inference_profile_id" {
  description = "Inference profile the extraction worker calls (BEDROCK_MODEL_ID)."
  type        = string
}
