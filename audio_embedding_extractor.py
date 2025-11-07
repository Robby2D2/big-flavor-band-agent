"""
Audio Embedding Extractor
Extracts multi-modal embeddings from audio files using librosa and transformers.
Combines traditional audio features (MFCCs, spectrograms, tempo, key) with 
deep learning embeddings for RAG system.
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import librosa
import json

logger = logging.getLogger("audio-embedding")

try:
    import torch
    from transformers import AutoProcessor, ClapModel
    CLAP_AVAILABLE = True
except ImportError:
    CLAP_AVAILABLE = False
    logger.warning("CLAP model not available. Install: pip install transformers torch")


class AudioEmbeddingExtractor:
    """
    Extract multi-modal embeddings from audio files.
    Combines traditional audio analysis with deep learning embeddings.
    """
    
    def __init__(self, use_clap: bool = True):
        """
        Initialize the audio embedding extractor.
        
        Args:
            use_clap: Whether to use CLAP model for audio embeddings (requires transformers + torch)
        """
        self.use_clap = use_clap and CLAP_AVAILABLE
        self.clap_model = None
        self.clap_processor = None
        
        if self.use_clap:
            try:
                logger.info("Loading CLAP model...")
                self.clap_model = ClapModel.from_pretrained("laion/clap-htsat-unfused")
                self.clap_processor = AutoProcessor.from_pretrained("laion/clap-htsat-unfused")
                # Move to GPU if available
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                self.clap_model = self.clap_model.to(self.device)
                logger.info(f"CLAP model loaded on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load CLAP model: {e}")
                self.use_clap = False
        
        logger.info(f"Audio embedding extractor initialized (CLAP: {self.use_clap})")
    
    def extract_librosa_features(self, audio_path: str, sr: int = 22050) -> Dict[str, Any]:
        """
        Extract traditional audio features using librosa.
        
        Args:
            audio_path: Path to audio file
            sr: Sample rate for loading audio
        
        Returns:
            Dictionary of audio features
        """
        try:
            # Load audio
            y, sr = librosa.load(audio_path, sr=sr, duration=30)  # First 30 seconds
            
            # Tempo and beat
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            
            # Key estimation using chroma
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            key_index = np.argmax(np.sum(chroma, axis=1))
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            estimated_key = keys[key_index]
            
            # MFCCs (Mel-frequency cepstral coefficients)
            mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            mfcc_mean = np.mean(mfccs, axis=1).tolist()
            mfcc_std = np.std(mfccs, axis=1).tolist()
            
            # Spectral features
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
            
            # Zero crossing rate (indicator of noisiness)
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            
            # RMS energy
            rms = librosa.feature.rms(y=y)[0]
            
            # Chroma features (pitch class profiles)
            chroma_stft = librosa.feature.chroma_stft(y=y, sr=sr)
            
            # Mel spectrogram
            mel_spec = librosa.feature.melspectrogram(y=y, sr=sr)
            mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)
            
            # Tonnetz (tonal centroid features)
            tonnetz = librosa.feature.tonnetz(y=y, sr=sr)
            
            return {
                'tempo': float(tempo),
                'estimated_key': estimated_key,
                'duration': float(librosa.get_duration(y=y, sr=sr)),
                
                # MFCCs - compact representation of spectral envelope
                'mfcc_mean': mfcc_mean,
                'mfcc_std': mfcc_std,
                
                # Spectral features - timbre characteristics
                'spectral_centroid_mean': float(np.mean(spectral_centroids)),
                'spectral_centroid_std': float(np.std(spectral_centroids)),
                'spectral_rolloff_mean': float(np.mean(spectral_rolloff)),
                'spectral_rolloff_std': float(np.std(spectral_rolloff)),
                'spectral_bandwidth_mean': float(np.mean(spectral_bandwidth)),
                'spectral_bandwidth_std': float(np.std(spectral_bandwidth)),
                
                # Energy features
                'rms_mean': float(np.mean(rms)),
                'rms_std': float(np.std(rms)),
                'zcr_mean': float(np.mean(zcr)),
                'zcr_std': float(np.std(zcr)),
                
                # Harmonic features
                'chroma_mean': np.mean(chroma_stft, axis=1).tolist(),
                'chroma_std': np.std(chroma_stft, axis=1).tolist(),
                
                # Tonal features
                'tonnetz_mean': np.mean(tonnetz, axis=1).tolist(),
                'tonnetz_std': np.std(tonnetz, axis=1).tolist(),
                
                # Summary statistics for mel spectrogram
                'mel_spec_mean': float(np.mean(mel_spec_db)),
                'mel_spec_std': float(np.std(mel_spec_db)),
            }
            
        except Exception as e:
            logger.error(f"Failed to extract librosa features from {audio_path}: {e}")
            return {}
    
    def extract_clap_embedding(self, audio_path: str, sr: int = 48000) -> Optional[np.ndarray]:
        """
        Extract audio embedding using CLAP (Contrastive Language-Audio Pretraining).
        
        Args:
            audio_path: Path to audio file
            sr: Sample rate (CLAP expects 48kHz)
        
        Returns:
            512-dimensional embedding vector or None
        """
        if not self.use_clap:
            return None
        
        try:
            # Load audio at CLAP's expected sample rate
            audio, _ = librosa.load(audio_path, sr=sr, duration=10)  # First 10 seconds
            
            # Process audio
            inputs = self.clap_processor(audios=audio, sampling_rate=sr, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Get embedding
            with torch.no_grad():
                audio_embed = self.clap_model.get_audio_features(**inputs)
            
            # Convert to numpy
            embedding = audio_embed.cpu().numpy()[0]
            
            # Normalize
            embedding = embedding / np.linalg.norm(embedding)
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to extract CLAP embedding from {audio_path}: {e}")
            return None
    
    def create_combined_embedding(
        self, 
        librosa_features: Dict[str, Any], 
        clap_embedding: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Create a combined embedding from librosa features and CLAP embedding.
        
        Args:
            librosa_features: Features extracted by librosa
            clap_embedding: Optional CLAP embedding vector
        
        Returns:
            Combined embedding vector suitable for pgvector storage
        """
        # Create feature vector from librosa features
        feature_vector = []
        
        # Add scalar features
        feature_vector.extend([
            librosa_features.get('tempo', 0) / 200.0,  # Normalize tempo
            librosa_features.get('spectral_centroid_mean', 0) / 5000.0,
            librosa_features.get('spectral_rolloff_mean', 0) / 10000.0,
            librosa_features.get('spectral_bandwidth_mean', 0) / 5000.0,
            librosa_features.get('rms_mean', 0),
            librosa_features.get('zcr_mean', 0),
        ])
        
        # Add MFCC means (13 coefficients)
        mfcc_mean = librosa_features.get('mfcc_mean', [0] * 13)
        feature_vector.extend(mfcc_mean[:13])
        
        # Add chroma means (12 pitch classes)
        chroma_mean = librosa_features.get('chroma_mean', [0] * 12)
        feature_vector.extend(chroma_mean[:12])
        
        # Add tonnetz means (6 dimensions)
        tonnetz_mean = librosa_features.get('tonnetz_mean', [0] * 6)
        feature_vector.extend(tonnetz_mean[:6])
        
        # Convert to numpy array
        feature_vector = np.array(feature_vector, dtype=np.float32)
        
        # Normalize librosa features
        feature_norm = np.linalg.norm(feature_vector)
        if feature_norm > 0:
            feature_vector = feature_vector / feature_norm
        
        # If CLAP embedding is available, concatenate
        if clap_embedding is not None:
            # Weight CLAP more heavily (it's trained on large datasets)
            combined = np.concatenate([
                feature_vector * 0.3,  # 37 dimensions from librosa
                clap_embedding * 0.7   # 512 dimensions from CLAP
            ])
        else:
            # Pad to standard dimension if CLAP not available
            # Use 549 dimensions (37 librosa + 512 CLAP)
            combined = np.concatenate([
                feature_vector,
                np.zeros(512, dtype=np.float32)
            ])
        
        # Final normalization
        combined = combined / np.linalg.norm(combined)
        
        return combined
    
    def extract_all_features(self, audio_path: str) -> Dict[str, Any]:
        """
        Extract all features and embeddings from an audio file.
        
        Args:
            audio_path: Path to audio file
        
        Returns:
            Dictionary containing:
            - librosa_features: Traditional audio features
            - clap_embedding: Deep learning embedding (if available)
            - combined_embedding: Combined embedding for vector search
        """
        audio_path = str(Path(audio_path).resolve())
        
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        logger.info(f"Extracting features from: {audio_path}")
        
        # Extract librosa features
        librosa_features = self.extract_librosa_features(audio_path)
        
        # Extract CLAP embedding if available
        clap_embedding = None
        if self.use_clap:
            clap_embedding = self.extract_clap_embedding(audio_path)
        
        # Create combined embedding
        combined_embedding = self.create_combined_embedding(
            librosa_features, 
            clap_embedding
        )
        
        result = {
            'audio_path': audio_path,
            'librosa_features': librosa_features,
            'clap_embedding': clap_embedding.tolist() if clap_embedding is not None else None,
            'combined_embedding': combined_embedding.tolist(),
            'embedding_dimension': len(combined_embedding)
        }
        
        logger.info(f"Extracted {len(combined_embedding)}-dimensional embedding")
        
        return result
    
    def batch_extract(self, audio_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Extract features from multiple audio files.
        
        Args:
            audio_paths: List of paths to audio files
        
        Returns:
            List of feature dictionaries
        """
        results = []
        total = len(audio_paths)
        
        for i, path in enumerate(audio_paths, 1):
            logger.info(f"Processing {i}/{total}: {Path(path).name}")
            try:
                features = self.extract_all_features(path)
                results.append(features)
            except Exception as e:
                logger.error(f"Failed to process {path}: {e}")
                continue
        
        return results
    
    def save_features_to_json(self, features: Dict[str, Any], output_path: str):
        """Save extracted features to JSON file."""
        with open(output_path, 'w') as f:
            json.dump(features, f, indent=2)
        logger.info(f"Saved features to {output_path}")


def main():
    """Test the audio embedding extractor."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if len(sys.argv) < 2:
        print("Usage: python audio_embedding_extractor.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    extractor = AudioEmbeddingExtractor(use_clap=True)
    features = extractor.extract_all_features(audio_file)
    
    print("\n=== Audio Features ===")
    print(f"Tempo: {features['librosa_features'].get('tempo', 'N/A')} BPM")
    print(f"Key: {features['librosa_features'].get('estimated_key', 'N/A')}")
    print(f"Duration: {features['librosa_features'].get('duration', 'N/A'):.2f} seconds")
    print(f"\nEmbedding dimension: {features['embedding_dimension']}")
    print(f"CLAP available: {features['clap_embedding'] is not None}")
    
    # Save to JSON
    output_path = audio_file.replace('.mp3', '_features.json')
    extractor.save_features_to_json(features, output_path)


if __name__ == '__main__':
    main()
