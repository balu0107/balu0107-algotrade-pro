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

variable "ssh_public_key" {
  description = "The public SSH key to inject into instances"
  type        = string
}