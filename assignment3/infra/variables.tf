variable "name" {
  type    = string
  default = "call-webhook"
}

variable "environment" {
  type    = string
  default = "sandbox"
}

variable "region" {
  type    = string
  default = "ap-south-1"
  validation {
    condition     = var.region == "ap-south-1"
    error_message = "Borrower PII must stay in India: region must be ap-south-1."
  }
}

variable "azs" {
  type    = list(string)
  default = ["ap-south-1a", "ap-south-1b"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "image_tag" {
  description = "Image tag for the first deploy. CI deploys later tags by registering new task definitions."
  type        = string
  default     = "bootstrap"
}

variable "crm_url" {
  type    = string
  default = "https://crm.example.internal/schedule"
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "min_tasks" {
  type    = number
  default = 2
}

variable "max_tasks" {
  type    = number
  default = 10
}

variable "requests_per_target_per_min" {
  description = "Target for ALBRequestCountPerTarget (a per-minute count). 6000/min = 100 rps per task -> ~5 tasks at the 500 rps peak."
  type        = number
  default     = 6000
}

variable "certificate_arn" {
  description = "ACM certificate for HTTPS. Empty = HTTP only (sandbox demo)."
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "owner/repo allowed to deploy through OIDC."
  type        = string
  default     = "kishan/kishan-predixion"
}

variable "create_github_oidc_provider" {
  description = "Set false if the account already has the token.actions.githubusercontent.com provider."
  type        = bool
  default     = true
}
