terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "ap-south-1" # Mumbai
}

# --- S3 BUCKET FOR TERRAFORM STATE ---
resource "aws_s3_bucket" "state_bucket" {
  bucket        = "algotrade-pro-terraform-state-bucket"
  force_destroy = true # Allows easy cleanup during your testing phase

  lifecycle {
    prevent_destroy = false
  }

  tags = { Name = "algotrade-terraform-state" }
}

resource "aws_s3_bucket_versioning" "enabled" {
  bucket = aws_s3_bucket.state_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "default" {
  bucket = aws_s3_bucket.state_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- DYNAMODB TABLE FOR STATE LOCKING ---
resource "aws_dynamodb_table" "state_lock" {
  name         = "algotrade-pro-lock-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = { Name = "algotrade-terraform-locks" }
}
