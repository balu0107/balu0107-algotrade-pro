output "s3_bucket_name" {
  description = "The name of the Terraform state S3 bucket"
  value       = aws_s3_bucket.state_bucket.id
}

output "dynamodb_table_name" {
  description = "The name of the Terraform state lock DynamoDB table"
  value       = aws_dynamodb_table.state_lock.id
}