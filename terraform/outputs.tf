output "k8s_master_public_ip" {
  description = "Public IP address of the single Kubernetes Master Node"
  value       = aws_instance.k8s_master.public_ip
}

output "k8s_worker_1_private_ip" {
  description = "Private IP address of Kubernetes Worker Node 1"
  value       = aws_instance.k8s_worker_1.private_ip
}

output "k8s_worker_2_private_ip" {
  description = "Private IP address of Kubernetes Worker Node 2"
  value       = aws_instance.k8s_worker_2.private_ip
}