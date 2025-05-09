# Stop the service if it’s running
Stop-Service -Name QSnippetService -Force

# Remove the service entry
Remove-Service -Name QSnippetService
