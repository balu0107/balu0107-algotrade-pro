output "master_public_ip" {
  value       = aws_instance.k8s_master.public_ip
  description = "Public IP address of the Kubernetes master node"
}

output "worker_public_ips" {
  value       = [aws_instance.k8s_worker_1.public_ip, aws_instance.k8s_worker_2.public_ip]
  description = "Public IP addresses of the Kubernetes worker nodes"
}