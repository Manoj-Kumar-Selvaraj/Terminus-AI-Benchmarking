resource "kubernetes_storage_class" "jenkins" { metadata { name = "jenkins-standard" } storage_provisioner = "kubernetes.io/aws-ebs" reclaim_policy = "Delete" }
locals { jenkins_home_volume = "emptyDir" }
