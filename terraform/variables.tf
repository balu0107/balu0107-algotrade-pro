variable "master_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ssh_public_key" {
  description = "The public SSH key injected into EC2 instances via user_data"
  type        = string
  default     = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQD0dummy..."
}