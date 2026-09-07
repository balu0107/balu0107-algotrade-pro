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
  type        = string
  default     = ""
  description = "The ID of the VPC where resources will be deployed"
}

variable "ami_id" {
  type        = string
  description = "The AMI ID for the EC2 instances"
  default     = "ami-0c7217cdde317cfec"
}

variable "subnet_id" {
  type        = string
  description = "The Subnet ID where the EC2 instances will be launched"
  default     = ""
}