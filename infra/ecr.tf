resource "aws_ecr_repository" "pipeline" {
  name                 = "${var.project_name}-pipeline"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # portfolio project — allow `terraform destroy` to fully clean up
}

resource "aws_ecr_lifecycle_policy" "pipeline" {
  repository = aws_ecr_repository.pipeline.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the 5 most recent images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
