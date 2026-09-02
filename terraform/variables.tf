variable "master_instance_type" {
  type    = string
  default = "t3.medium" # Paid 4GB RAM for Master Control Plane
}

variable "worker_instance_type" {
  type    = string
  default = "t3.micro"  # Free Tier 1GB RAM for Workers
}

variable "key_name" {
  type    = string
  default = "devops-key"
}
