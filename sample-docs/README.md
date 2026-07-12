# Beispiel-Dokumente

In dieses Verzeichnis gehören **keine** Dateien ins Repository – es dient nur
als Ablage für lokale Test-PDFs.

Die eigentlichen Anwendungshinweise (z. B. BFS-Merkblätter, technische
Richtlinien des Maler- und Lackiererhandwerks) werden **nicht** eingecheckt,
sondern in den S3-Bucket hochgeladen:

```bash
# Bucket-Name stammt aus dem Stack-Output "DocumentsBucketName"
aws s3 cp mein-merkblatt.pdf \
  s3://<DocumentsBucketName>/documents/ \
  --region eu-central-1
```

Sobald ein PDF unter dem Prefix `documents/` landet, startet automatisch ein
Bedrock-Ingestion-Job und das Dokument fließt in die Wissensbasis ein.
