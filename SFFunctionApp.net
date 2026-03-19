using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.WebJobs;
using Microsoft.Azure.WebJobs.Extensions.Http;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Newtonsoft.Json;
using Microsoft.WindowsAzure.Storage.Blob;
using Microsoft.WindowsAzure.Storage;
using System.Collections.Generic;
using Renci.SshNet;

namespace SFFunctionAppBC
{
    public static class ImportProductSFtp
    {
        [FunctionName("SFSTPApp")]
        public static async Task<IActionResult> Upload([HttpTrigger(AuthorizationLevel.Function, "post", Route = null)] HttpRequest req,ILogger log)
        {
            log.LogInformation("C# HTTP trigger function processed a request.");

            string requestBody = await new StreamReader(req.Body).ReadToEndAsync();
            dynamic data = JsonConvert.DeserializeObject(requestBody);

            string base64String = data.base64;
            string fileName = data.fileName;
            string fileType = data.fileType;
            string fileExt = data.fileExt;

            string BLOBStorageConnectionString = data.BLOBStorageConnectionString;
            string storageAccountContainer = data.storageAccountContainer;

            string sftpAddress = data.sftpAddress;
            string sftpPort = data.sftpPort;
            string sftpUsername = data.sftpUsername;
            string sftpPassword = data.sftpPassword;
            string sftpPath = data.sftpPath;


            //string BLOBStorageConnectionString = "BlobEndpoint=https://straightforwardblob.blob.core.windows.net/;QueueEndpoint=https://straightforwardblob.queue.core.windows.net/;FileEndpoint=https://straightforwardblob.file.core.windows.net/;TableEndpoint=https://straightforwardblob.table.core.windows.net/;SharedAccessSignature=sv=2021-12-02&ss=bfqt&srt=sco&sp=rwdlacupiytfx&se=2023-03-28T10:21:01Z&st=2023-03-10T02:21:01Z&spr=https,http&sig=QxMz1JlUpvi5MndatXBmwb6SeNgwp%2FWFCyWnf3SFB%2Bs%3D";
            //string storageAccountContainer = "d365bcfiles";

            //string sftpAddress = "122.54.93.81";
            //string sftpPort = "22";
            //string sftpUsername = "kation";
            //string sftpPassword = "kation123";
            //string sftpPath = "/home/kation";


            Uri uri = await UploadBlobAsync(base64String, fileName, fileType, fileExt, BLOBStorageConnectionString, storageAccountContainer);
            //Upload to SFTP
            fileName = await UploadFileToSFTP(uri, fileName, BLOBStorageConnectionString, storageAccountContainer, sftpAddress, sftpPort, sftpUsername, sftpPassword, sftpPath);

            return fileName != null
                ? (ActionResult)new OkObjectResult($"File {fileName} stored. URI = {uri}")
                : new BadRequestObjectResult("Error on input parameter (object)");
        }

        public static async Task<Uri> UploadBlobAsync(string base64String, string fileName, string fileType, string fileExtensio, string BLOBStorageConnectionString, string storageAccountContainer)
        {
            string contentType = fileType;
            byte[] fileBytes = Convert.FromBase64String(base64String);

            CloudStorageAccount storageAccount = CloudStorageAccount.Parse(BLOBStorageConnectionString);
            CloudBlobClient client = storageAccount.CreateCloudBlobClient();
            CloudBlobContainer container = client.GetContainerReference(storageAccountContainer);

            await container.CreateIfNotExistsAsync(
              BlobContainerPublicAccessType.Blob,
              new BlobRequestOptions(),
              new OperationContext());
            CloudBlockBlob blob = container.GetBlockBlobReference(fileName);
            blob.Properties.ContentType = contentType;

            using (Stream stream = new MemoryStream(fileBytes, 0, fileBytes.Length))
            {
                await blob.UploadFromStreamAsync(stream).ConfigureAwait(false);
            }

            return blob.Uri;
        }
        private static async Task<string> UploadFileToSFTP(Uri uri, string targetFileName, string storageConnectionString, string storageAccountContainer, string sftpAddress, string sftpPort, string sftpUsername, string sftpPassword,string sftpPath)
        {
            try
            {
                string sourceFileAbsolutePath = uri.ToString();
                //SFTP Parameters (read it from configurations or Azure KeyVault)

                var memoryStream = new MemoryStream();

                CloudStorageAccount storageAccount;
                if (CloudStorageAccount.TryParse(storageConnectionString, out storageAccount))
                {
                    CloudBlobClient cloudBlobClient = storageAccount.CreateCloudBlobClient();
                    CloudBlobContainer cloudBlobContainer = cloudBlobClient.GetContainerReference(storageAccountContainer);

                    CloudBlockBlob cloudBlockBlobToTransfer = cloudBlobContainer.GetBlockBlobReference(new CloudBlockBlob(uri).Name);
                    await cloudBlockBlobToTransfer.DownloadToStreamAsync(memoryStream);
                }

                //read mstream from top
                memoryStream.Seek(0, SeekOrigin.Begin);

                var methods = new List<AuthenticationMethod>();
                methods.Add(new PasswordAuthenticationMethod(sftpUsername, sftpPassword));

                //Connects to the SFTP Server and uploads the file 
                Renci.SshNet.ConnectionInfo con = new Renci.SshNet.ConnectionInfo(sftpAddress, sftpUsername, new PasswordAuthenticationMethod(sftpUsername, sftpPassword));

                using (var client = new SftpClient(con))
                {
                    client.Connect();
                    client.UploadFile(memoryStream, $"/{sftpPath}/{targetFileName}");
                    client.Disconnect();
                    return targetFileName;
                }

            }
            catch (IOException ioex)
            {
                Console.WriteLine("Error: {0}", ioex.Message);
                return null;
            }
            catch (System.Net.Sockets.SocketException)
            {
                Console.WriteLine("Error: {0}", "Invalid IP Address or Hostname");
                return null;
            }
            catch (Renci.SshNet.Common.SshAuthenticationException ex)
            {
                Console.WriteLine("Error: {0}", ex.Message);
                return null;
            }
            catch (Exception ex)
            {
                Console.WriteLine("Error: {0}", ex.Message);
                return null;
            }
        }
    }

}