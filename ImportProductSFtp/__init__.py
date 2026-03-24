import logging
import base64
import io
import azure.functions as func
from azure.storage.blob import BlobServiceClient, ContentSettings
import paramiko
import json


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function processed a request.")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body.", status_code=400)

    # Parse request body
    base64_string         = body.get("base64")
    file_name             = body.get("fileName")
    file_type             = body.get("fileType")
    file_ext              = body.get("fileExt")
    blob_conn_string      = body.get("BLOBStorageConnectionString")
    storage_container     = body.get("storageAccountContainer")
    sftp_address          = body.get("sftpAddress")
    sftp_port             = int(body.get("sftpPort", 22))
    sftp_username         = body.get("sftpUsername")
    sftp_password         = body.get("sftpPassword")
    sftp_path             = body.get("sftpPath")

    # Upload to Azure Blob Storage
    blob_url = upload_blob(
        base64_string, file_name, file_type,
        blob_conn_string, storage_container
    )

    if blob_url is None:
        return func.HttpResponse("Failed to upload to Blob Storage.", status_code=500)

    # Upload from Blob to SFTP
    result = upload_to_sftp(
        blob_conn_string, storage_container, file_name,
        sftp_address, sftp_port, sftp_username, sftp_password, sftp_path
    )

    if result:
        return func.HttpResponse(
            f"File {file_name} stored. URI = {blob_url}",
            status_code=200
        )
    else:
        return func.HttpResponse("Error uploading file to SFTP.", status_code=400)


def upload_blob(base64_string: str, file_name: str, content_type: str,
                conn_string: str, container_name: str) -> str | None:
    """Decode base64 and upload to Azure Blob Storage. Returns the blob URL."""
    try:
        file_bytes = base64.b64decode(base64_string)

        blob_service_client = BlobServiceClient.from_connection_string(conn_string)
        container_client = blob_service_client.get_container_client(container_name)

        # Create container if it doesn't exist
        try:
            container_client.create_container()
        except Exception:
            pass  # Already exists

        blob_client = container_client.get_blob_client(file_name)
        blob_client.upload_blob(
            io.BytesIO(file_bytes),
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type)
        )

        return blob_client.url

    except Exception as e:
        logging.error(f"Blob upload error: {e}")
        return None


def upload_to_sftp(conn_string: str, container_name: str, file_name: str,
                   sftp_address: str, sftp_port: int, sftp_username: str,
                   sftp_password: str, sftp_path: str) -> bool:
    """Download blob into memory and upload to SFTP server."""
    try:
        # Download blob into memory
        blob_service_client = BlobServiceClient.from_connection_string(conn_string)
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=file_name
        )

        memory_stream = io.BytesIO()
        download_stream = blob_client.download_blob()
        download_stream.readinto(memory_stream)
        memory_stream.seek(0)

        # Connect and upload via SFTP
        transport = paramiko.Transport((sftp_address, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)

        with paramiko.SFTPClient.from_transport(transport) as sftp:
            remote_path = f"{sftp_path.rstrip('/')}/{file_name}"
            sftp.putfo(memory_stream, remote_path)

        transport.close()
        logging.info(f"File {file_name} uploaded to SFTP at {remote_path}")
        return True

    except IOError as e:
        logging.error(f"IO Error: {e}")
    except paramiko.AuthenticationException as e:
        logging.error(f"SFTP Auth Error: {e}")
    except Exception as e:
        logging.error(f"SFTP Error: {e}")

    return False