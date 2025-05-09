New-Service -Name QSnippetService `
  -BinaryPathName "C:\Program Files\QSnippet\qsnippet_service.exe --config C:\Program Files\QSnippet\snippets.yaml" `
  -DisplayName "QSnippetService" `
  -Description "Watches for snippet triggers and expands text globally." `
  -StartupType Automatic
Start-Service QSnippetService