output "nat_instance_public_ip" {
  description = "Public IP of the NAT Instance"
  value       = aws_instance.nat_instance.public_ip
}

output "k8s_master_private_ip" {
  description = "Private IP of the Master Node"
  value       = aws_instance.k8s_master.private_ip
}

output "k8s_worker_1_private_ip" {
  description = "Private IP of Worker Node 1"
  value       = aws_instance.k8s_worker_1.private_ip
}

output "k8s_worker_2_private_ip" {
  description = "Private IP of Worker Node 2"
  value       = aws_instance.k8s_worker_2.private_ip
}
