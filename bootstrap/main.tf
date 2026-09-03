provider "aws" {
  region = "ap-south-1"
}

resource "aws_s3_bucket" "state_bucket" {
  bucket        = "algotrade-pro-terraform-state-bucket"
  force_destroy = false

  lifecycle {
    prevent_destroy = true
    ignore_changes  = all
  }
}

resource "aws_dynamodb_table" "state_lock" {
  name         = "algotrade-pro-lock-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  lifecycle {
    ignore_changes = all
  }
}