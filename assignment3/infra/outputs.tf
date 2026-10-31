output "health_url" {
  value = "http://${aws_lb.main.dns_name}/health"
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "crm_secret_arn" {
  value = aws_secretsmanager_secret.crm_token.arn
}

output "github_deploy_role_arn" {
  value = aws_iam_role.github_deploy.arn
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}

output "ecs_service" {
  value = aws_ecs_service.app.name
}
