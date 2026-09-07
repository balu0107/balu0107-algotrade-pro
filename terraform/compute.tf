resource "aws_security_group" "k8s_cluster_sg" {
  name        = "k8s-cluster-sg"
  description = "Security group for Kubernetes cluster allowing SSH, API server, and NodePort traffic"
  vpc_id      = var.vpc_id

  # SSH Access
  ingress {
    description = "Allow SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Kubernetes API Server
  ingress {
    description = "Allow Kubernetes API Server"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Frontend NodePort
  ingress {
    description = "Allow Frontend NodePort 31987"
    from_port   = 31987
    to_port     = 31987
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Internal Cluster Traffic
  ingress {
    description = "Allow internal VPC traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["10.0.0.0/16"]
  }

  # Outbound Access
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "k8s-cluster-sg"
  }
}

resource "aws_instance" "k8s_master" {
  ami                         = var.ami_id
  instance_type               = var.master_instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.k8s_cluster_sg.id]
  associate_public_ip_address = true
  key_name                    = var.key_name

  tags = {
    Name = "k8s-master"
  }
}

resource "aws_instance" "k8s_worker_1" {
  ami                         = var.ami_id
  instance_type               = var.worker_instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.k8s_cluster_sg.id]
  associate_public_ip_address = true
  key_name                    = var.key_name

  tags = {
    Name = "k8s-worker-1"
  }
}

resource "aws_instance" "k8s_worker_2" {
  ami                         = var.ami_id
  instance_type               = var.worker_instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.k8s_cluster_sg.id]
  associate_public_ip_address = true
  key_name                    = var.key_name

  tags = {
    Name = "k8s-worker-2"
  }
}