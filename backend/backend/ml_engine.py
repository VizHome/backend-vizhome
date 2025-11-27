import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as transforms
from PIL import Image
import io

# --- 1. Votre Architecture du Modèle (Nettoyée) ---

class UNet2D(nn.Module):
    def __init__(self, in_channels=3, out_channels=3):
        super(UNet2D, self).__init__()
        # Encoder
        self.encoder1 = self.conv_block(in_channels, 64)
        self.encoder2 = self.conv_block(64, 128)
        self.encoder3 = self.conv_block(128, 256)
        self.encoder4 = self.conv_block(256, 512)
        
        self.pool = nn.MaxPool2d(2)
        
        # Decoder
        self.decoder1 = self.upconv_block(512, 256)
        self.decoder2 = self.upconv_block(256, 128)
        self.decoder3 = self.upconv_block(128, 64)
        self.decoder4 = self.upconv_block(64, out_channels)
    
    def conv_block(self, in_channels, out_channels):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.ReLU()
        )
    
    def upconv_block(self, in_channels, out_channels):
        return nn.Sequential(
            nn.ConvTranspose2d(in_channels, out_channels, kernel_size=2, stride=2),
            nn.ReLU(),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.ReLU()
        )

    def forward(self, x):
        # Encoder path
        e1 = self.encoder1(x)
        e2 = self.encoder2(self.pool(e1))
        e3 = self.encoder3(self.pool(e2))
        e4 = self.encoder4(self.pool(e3))

        # Decoder path
        d1 = self.decoder1(e4)
        
        # Interpolate e3 to match d1's size
        e3 = F.interpolate(e3, size=d1.shape[2:], mode='bilinear', align_corners=False)
        d2 = self.decoder2(d1 + e3)
        
        e2 = F.interpolate(e2, size=d2.shape[2:], mode='bilinear', align_corners=False)
        d3 = self.decoder3(d2 + e2)
        
        e1 = F.interpolate(e1, size=d3.shape[2:], mode='bilinear', align_corners=False)
        d4 = self.decoder4(d3 + e1)

        # VOTRE CONTRAINTE : Output size forced to (180, 300) -> (Height, Width)
        d4 = F.interpolate(d4, size=(180, 300), mode='bilinear', align_corners=False)

        return d4

# --- 2. Initialisation du Modèle (Singleton) ---

# Détection automatique du GPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Instanciation
model = UNet2D(in_channels=3, out_channels=3).to(device)

# Chargement des poids (Weights)
MODEL_PATH = r'D:\Documents\DATA\2024-11-19_VizHome\backend-vizhome\backend\backend\model_ia\unet_model_epoch10.pth' # <--- Modifiez ceci

try:
    # map_location est important si vous avez entraîné sur GPU et déployez sur CPU
    state_dict = torch.load(MODEL_PATH, map_location=device)
    model.load_state_dict(state_dict)
    model.eval() # Mode évaluation (très important)
    print(f"Modèle chargé sur {device}")
except FileNotFoundError:
    print(f"ATTENTION : Fichier modèle non trouvé à : {MODEL_PATH}")
except Exception as e:
    print(f"Erreur chargement modèle : {e}")


# --- 3. Fonction de Traitement pour la Vue Django ---

def process_image_with_unet(image_bytes):
    """
    Prend les bytes de l'image brute, applique le modèle, retourne les bytes de l'image résultante.
    """
    # A. Préparation (Pre-processing)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # Redimensionnement : On doit matcher les attentes du modèle ou s'en rapprocher
    # Votre modèle force la sortie à (180, 300) (H, W).
    # Il est prudent de redimensionner l'entrée à la même taille pour éviter les distorsions.
    transform = transforms.Compose([
        transforms.Resize((180, 300)), 
        transforms.ToTensor(),
    ])
    
    # Ajout dimension batch : [C, H, W] -> [1, C, H, W]
    input_tensor = transform(image).unsqueeze(0).to(device)

    # B. Inférence
    with torch.no_grad():
        output_tensor = model(input_tensor)

    # C. Post-processing
    output_tensor = output_tensor.squeeze(0).cpu() # Retirer batch
    
    # Si votre modèle sort des valeurs non bornées, on peut vouloir clipper entre 0 et 1
    output_tensor = torch.clamp(output_tensor, 0, 1)
    
    to_pil = transforms.ToPILImage()
    result_image = to_pil(output_tensor)

    # D. Conversion en Bytes
    img_byte_arr = io.BytesIO()
    result_image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr