variable "master_instance_type" {
  type    = string
  default = "t3.medium"
}

variable "worker_instance_type" {
  type    = string
  default = "t3.micro"
}

variable "ssh_public_key" {
  description = "Injected transient public key"
  type        = string
}