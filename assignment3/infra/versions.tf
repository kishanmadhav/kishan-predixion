terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
  # For team/CI use, switch to remote state:
  #   terraform init -backend-config="bucket=..." -backend-config="key=call-webhook/terraform.tfstate" \
  #                  -backend-config="region=ap-south-1" -backend-config="use_lockfile=true"
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Service     = var.name
      Environment = var.environment
      ManagedBy   = "terraform"
      DataClass   = "pii-india" # phone numbers stay in ap-south-1
    }
  }
}
