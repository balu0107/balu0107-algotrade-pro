terraform {
  backend "s3" {
    bucket         = "algotrade-pro-terraform-state-bucket"
    key            = "main/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "algotrade-pro-lock-table"
  }
}
