resource "null_resource" "xpk_rewrite" {
  provisioner "local-exec" {
    command = "echo 'Terraform is better!'"
  }
}
