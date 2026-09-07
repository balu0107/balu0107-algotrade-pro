variable "master_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "key_name" {
  type    = string
  default = "devops-key"
}

variable "vpc_id" {
  type    = string
  default = ""
  description = "The ID of the VPC where resources will be deployed"
}