"""Tests pour PresignedUploadRequestSerializer — focus hardening B2.

Couvre :
- Whitelist extension
- Sanitisation filename (path traversal, caractères dangereux)
- Limite taille max
- Cohérence content-type ↔ extension
- Normalisation MIME suspect → octet-stream
"""

from __future__ import annotations

from apps.projects.serializers import PresignedUploadRequestSerializer


def _payload(**overrides):
    base = {
        'name': 'Maquette',
        'file_name': 'maquette.glb',
        'file_size_bytes': 1024 * 1024,  # 1 MB
        'content_type': 'model/gltf-binary',
    }
    base.update(overrides)
    return base


class TestExtensionWhitelist:
    def test_glb_accepted(self):
        ser = PresignedUploadRequestSerializer(data=_payload())
        assert ser.is_valid(), ser.errors

    def test_gltf_accepted(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='m.gltf', content_type='model/gltf+json'),
        )
        assert ser.is_valid(), ser.errors

    def test_obj_accepted(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='m.obj', content_type='text/plain'),
        )
        assert ser.is_valid(), ser.errors

    def test_fbx_accepted(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='m.fbx', content_type='application/octet-stream'),
        )
        assert ser.is_valid(), ser.errors

    def test_stl_accepted(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='m.stl', content_type='model/stl'),
        )
        assert ser.is_valid(), ser.errors

    def test_pdf_rejected(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='dangereux.pdf'),
        )
        assert not ser.is_valid()
        assert 'file_name' in ser.errors

    def test_exe_rejected(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='virus.exe'),
        )
        assert not ser.is_valid()

    def test_no_extension_rejected(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='sansExtension'),
        )
        assert not ser.is_valid()


class TestFilenameSanitization:
    def test_path_traversal_rejected(self):
        """Refuse `../` et chemins absolus pour ne pas écrire hors bucket."""
        for bad in (
            '../etc/passwd.glb',
            '../../home/user.glb',
            '/etc/secret.glb',
            'a/b/c.glb',
        ):
            ser = PresignedUploadRequestSerializer(data=_payload(file_name=bad))
            assert not ser.is_valid(), f'Devrait rejeter {bad}'

    def test_control_chars_rejected(self):
        for bad in ('m\x00.glb', 'm\n.glb', 'm\r.glb', 'm\\.glb'):
            ser = PresignedUploadRequestSerializer(data=_payload(file_name=bad))
            assert not ser.is_valid(), f'Devrait rejeter {bad!r}'

    def test_leading_dot_rejected(self):
        """Pas de fichier caché : on évite `.glb` (juste l'extension)."""
        ser = PresignedUploadRequestSerializer(data=_payload(file_name='.glb'))
        assert not ser.is_valid()

    def test_basename_stripped(self):
        """Un filename contenant un dossier `models/foo.glb` est rejeté
        par la check `/` dans la sanitisation."""
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_name='models/foo.glb'),
        )
        # `/` est dans la blacklist → rejeté
        assert not ser.is_valid()


class TestFileSizeLimit:
    def test_size_zero_rejected(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_size_bytes=0),
        )
        assert not ser.is_valid()

    def test_size_above_limit_rejected(self):
        """100 MB max — un fichier de 200 MB doit être refusé."""
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_size_bytes=200 * 1024 * 1024),
        )
        assert not ser.is_valid()
        assert 'file_size_bytes' in ser.errors

    def test_size_at_limit_accepted(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(file_size_bytes=PresignedUploadRequestSerializer.MAX_FILE_SIZE_BYTES),
        )
        assert ser.is_valid(), ser.errors


class TestContentTypeConsistency:
    def test_html_content_type_for_glb_rejected(self):
        """Un .glb avec content-type text/html est un signe de tentative
        d'upload de page d'attaque."""
        ser = PresignedUploadRequestSerializer(
            data=_payload(content_type='text/html'),
        )
        assert not ser.is_valid()
        assert 'content_type' in ser.errors

    def test_javascript_content_type_rejected(self):
        ser = PresignedUploadRequestSerializer(
            data=_payload(content_type='application/javascript'),
        )
        assert not ser.is_valid()

    def test_unknown_content_type_normalized_to_octet_stream(self):
        """Un type incohérent mais pas malveillant est normalisé."""
        ser = PresignedUploadRequestSerializer(
            data=_payload(content_type='image/png'),
        )
        assert ser.is_valid(), ser.errors
        assert ser.validated_data['content_type'] == 'application/octet-stream'

    def test_default_content_type_accepted_for_any_ext(self):
        """`application/octet-stream` est toléré partout (fallback browser)."""
        for ext in ('glb', 'gltf', 'obj', 'fbx', 'stl'):
            ser = PresignedUploadRequestSerializer(
                data=_payload(
                    file_name=f'm.{ext}',
                    content_type='application/octet-stream',
                ),
            )
            assert ser.is_valid(), f'.{ext} devrait accepter octet-stream'
