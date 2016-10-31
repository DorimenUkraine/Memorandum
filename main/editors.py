from django.shortcuts import render, redirect
from django.template import Context
from django.http import HttpResponse
from django.conf import settings
from PIL import Image
<<<<<<< HEAD
=======
# import io
>>>>>>> 104f5b5247e70e6bbbdfec6c1ed5bdab496e26ef
import importlib
import zlib
import re
import datetime
import mimetypes
import os.path
from . import items
from . import views
from . import models
from . import item_reps
from .permissions import ALL_PERMISSIONS

mimetypes.init()


def get_editor(name):
    all_editors = get_all_editors()
    editor = UniversalFileEditor
    for possibleEditor in all_editors:
        if possibleEditor.name == name:
            editor = possibleEditor
            break
    return editor


def get_all_editors():
    default_editors = [
        'CodeEditor',
        'MarkdownEditor',
        'DirectoryEditor',
        'ImageEditor',
        'AudioEditor',
        'VideoEditor',
        'OnlyOfficeEditor',
        'PdfEditor',
        'UniversalFileEditor'
    ]
    if hasattr(settings, 'EDITORS') and len(settings.EDITORS) > 0:
        editor_names = settings.EDITORS
    else:
        editor_names = default_editors
    initialized_editors = []
    for editor_name in editor_names:
        module_path_parts = editor_name.rsplit(".", 1)
        if len(module_path_parts) > 1:
            module = importlib.import_module(module_path_parts[0])
            editor_name = module_path_parts[1]
            editor_constructor = getattr(module, editor_name)
            initialized_editors.append(editor_constructor())
        else:
            editor = globals()[editor_name]()
            initialized_editors.append(editor)
    return initialized_editors


def get_default_for(item):
    all_editors = get_all_editors()
    for possibleEditor in all_editors:
        if possibleEditor.can_handle(item):
            default_editor = possibleEditor
            break
    return default_editor


# abstract editor
class Editor:
    def __init__(self):
        self.name = "editor"
        # list of extensions that can be handle
        self.extensions = []
        self.thumbnail = "blocks/thumbnails/file.html"

    # returns if needed action was not found
    def not_exists(self):
        return HttpResponse("No such action")

    @classmethod
    def show(cls, item, request):
        return HttpResponse("Sup, i handled " + item.name)

    @classmethod
    def rename(cls, item, request):
        new_name = request.POST.get('name', item.name)
        if not item.is_root:
            item.rename(new_name)
        return redirect(views.item_handler, user_id=item.owner.id, relative_path=item.rel_path)

    @classmethod
    def share(cls, item, request):
        user_email = request.POST.get('target', "")
        sharing_type = int(request.POST.get('type', "-1"))
        rel_path = item.rel_path

        if sharing_type not in ALL_PERMISSIONS:
            raise RuntimeError('Invalid sharing type')

        share_with = models.CustomUser.objects.get(email=user_email)
        if share_with.id == request.user.id:
            raise RuntimeError('Can not share to yourself')

        sharing_note, create = models.Sharing.objects.get_or_create(owner=item.owner, item=rel_path,
                                                                    shared_with=share_with,
                                                                    defaults={'permissions': 0})
        sharing_note.permissions = sharing_type
        sharing_note.save()

        return redirect(views.item_handler, user_id=item.parent.owner.id, relative_path=item.rel_path)

    @classmethod
    def unshare(cls, item, request):
        sharing_id = request.GET.get('id', None)

        if not sharing_id:
            raise ValueError('Invalid sharing id')

        sharing = models.Sharing.objects.get(id=sharing_id)

        if sharing.owner != request.user:
            raise PermissionError('Only owner can remove sharings')

        sharing.delete()
        return redirect(views.item_handler, user_id=item.parent.owner.id, relative_path=item.rel_path)

    @classmethod
    def delete(cls, item, request):
        item.delete()
        return redirect(views.item_handler, user_id=item.parent.owner.id, relative_path=item.parent.rel_path)


# editor for directories
class DirectoryEditor(Editor):
    def __init__(self):
        super(DirectoryEditor, self).__init__()
        self.name = "directory"
        self.extensions = [""]
        self.thumbnail = "blocks/thumbnails/dir.html"

    def can_handle(self, item):
        if item.is_dir:
            return True
        else:
            return False

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.DirectoryRepresentation(item)
        child_list = item.children
        child_files = []
        child_dirs = []
        for child in child_list:
            if child.is_dir:
                child_dirs.append(item_reps.DirectoryRepresentation(child))
            else:
                child_files.append(item_reps.FileRepresentation(child))
        context = Context({'item_rep': item_rep, 'child_dirs': child_dirs, 'child_files': child_files,})
        return render(request, "dir.html", context)

    @classmethod
    def download(cls, item, request):
        data = item.make_zip()
        response = HttpResponse(data, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="%s"' % (item.name + '.zip')
        return response

    @classmethod
    def upload(cls, item, request):
        if request.method == 'POST' and 'file' in request.FILES:
            uploaded_file = request.FILES['file']
            new_rel_path = item.make_path_to_new_item(uploaded_file.name)
            new_item = items.FileItem(item.owner, new_rel_path)
            new_item.write_file(uploaded_file.chunks())
        return redirect(views.item_handler, user_id=item.parent.owner.id, relative_path=item.parent.rel_path)

    @classmethod
    def create_new(cls, item, request):
        name = request.POST.get('name', "")
        item_type = request.POST.get('item_type', "file")
        default_name = "new_file"
        if item_type == "directory":
            default_name = "new_folder"
        if name == "":
            name = default_name
        new_rel_path = item.make_path_to_new_item(name)
        new_item = items.get_instance_by_type(item_type, item.absolute_path, item.owner, new_rel_path)
        if new_item is not None:
            new_item.create_empty()
        return redirect(views.item_handler, user_id=item.owner.id, relative_path=item.rel_path)


# common editor for files
class FileEditor(Editor):
    def __init__(self):
        super(FileEditor, self).__init__()
        self.name = "file"
        self.extensions = [".txt", ".hex", ".bin", ".ini"]
        self.thumbnail = "blocks/thumbnails/file.html"

    def can_handle(self, item):
        extension = item.extension.lower()
        if extension in self.extensions and not item.is_dir:
            return True
        else:
            return False

    @classmethod
    def raw(cls, item, request):
        data = item.read_byte()
        return HttpResponse(data, content_type=item.mime)

    @classmethod
    def download(cls, item, request):
        content = item.read_byte()
        response = HttpResponse(content, content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename=' + item.name
        response['X-Sendfile'] = item.name
        return response


class UniversalFileEditor(FileEditor):
    def __init__(self):
        super(UniversalFileEditor, self).__init__()
        self.name = "universal"

    def can_handle(self, item):
        if not item.is_dir:
            return True
        else:
            return False

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/default.html", context)


class CodeEditor(FileEditor):
    def __init__(self):
        super(CodeEditor, self).__init__()
        self.name = "code"
        self.extensions = [".txt", ".hex", ".bin", ".ini", ""]

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/code.html", context)


class MarkdownEditor(FileEditor):
    def __init__(self):
        super(MarkdownEditor, self).__init__()
        self.name = "markdown"
        self.extensions = [".markdown", ".md"]

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/md.html", context)


class ImageEditor(FileEditor):
    THUMBS_FOLDER = 'thumbs'
    THUMB_SIZE = (128, 128)
    THUMB_FORMAT = 'PNG'
    THUMBS_CACHE_SECONDS = 604800

    def __init__(self):
        super(ImageEditor, self).__init__()
        self.name = "image"
        self.extensions = [".jpg", ".bmp", ".gif", ".png"]
        self.thumbnail = "blocks/thumbnails/image.html"

    @classmethod
    def preview(cls, item, request):
        media_directory_item = items.DirectoryItem(item.owner, item.parent.rel_path,
                                                   os.path.join(settings.MEDIA_ROOT,
                                                                ImageEditor.THUMBS_FOLDER,
                                                                str(item.owner.id)))
        if not media_directory_item.exists and not media_directory_item.is_dir:
            media_directory_item.create_empty()

        preview_item = items.FileItem(item.owner, item.name, media_directory_item.absolute_path)

        if not preview_item.exists or preview_item.modified_time < item.modified_time:
            image = Image.open(item.absolute_path)
            image.thumbnail(ImageEditor.THUMB_SIZE, Image.ANTIALIAS)
            image.save(preview_item.absolute_path, format=ImageEditor.THUMB_FORMAT)

        response = ImageEditor.raw(preview_item, request)
        response['Cache-Control'] = 'public, max-age:{}'.format(ImageEditor.THUMBS_CACHE_SECONDS)
        return response

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/image.html", context)


class AudioEditor(FileEditor):
    def __init__(self):
        super(AudioEditor, self).__init__()
        self.name = "audio"
        self.extensions = [".mp3", ".wav", ".m3u", ".ogg"]
        self.thumbnail = "blocks/thumbnails/file.html"

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/audio.html", context)


class VideoEditor(FileEditor):
    def __init__(self):
        super(VideoEditor, self).__init__()
        self.name = "video"
        self.extensions = [".mp4", ".avi", ".mov", ".webm"]
        self.thumbnail = "blocks/thumbnails/file.html"

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/video.html", context)


class OnlyOfficeEditor(FileEditor):
    def __init__(self):
        super(OnlyOfficeEditor, self).__init__()
        self.name = "office"
        self.extensions = OnlyOfficeEditor.get_all_extensions()
        self.thumbnail = "blocks/thumbnails/file.html"

    @classmethod
    def show(cls, item, request):
        now = datetime.datetime.now()
        curr_date = str(now.day) + "." + str(now.month) + "." + str(now.year)
        api_src = settings.ONLYOFFICE_SERV_API_URL
        item_rep = item_reps.FileRepresentation(item)
        last_breadcrumb = len(item_rep.breadcrumbs) - 1
        item_url = item_rep.url
        parent_url = item_rep.breadcrumbs[last_breadcrumb].url
        client_ip = request.META['REMOTE_ADDR']
        doc_editor_key = OnlyOfficeEditor.get_doc_editor_key(client_ip, item_rep.name)
        doc_type = OnlyOfficeEditor.get_document_type(item)
        ext = item_rep.item.extension.lstrip(".")
        context = Context({'item_rep': item_rep, 'api_src': api_src,
                           'doc_type': doc_type, 'doc_editor_key': doc_editor_key,
                           'client_ip': client_ip, 'parent_url': parent_url,
                           'curr_date': curr_date, 'ext': ext, 'item_url': item_url})
        return render(request, "files/office.html", context)

    @classmethod
    def get_document_type(cls, item):
        ext = "." + item.extension
        if item.extension in settings.EXTS_DOCUMENT:
            return "text"
        elif item.extension in settings.EXTS_SPREADSHEET:
            return "spreadsheet"
        elif item.extension in settings.EXTS_PRESENTATION:
            return "presentation"
        else:
            return ""

    @classmethod
    def get_all_extensions(cls):
        extensions = []
        extensions.extend(settings.EXTS_DOCUMENT)
        extensions.extend(settings.EXTS_SPREADSHEET)
        extensions.extend(settings.EXTS_PRESENTATION)
        return extensions

    @classmethod
    def get_doc_editor_key(cls, ip, name):
        return OnlyOfficeEditor.generate_revision_id(ip + "/" + name)

    @classmethod
    def generate_revision_id(cls, key):
        if len(key) > 20:
            key = zlib.crc32(key.encode('utf-8'))
        key = re.sub("[^0-9-.a-zA-Z_=]", "_", str(key))
        limits = [20, len(key)]
        key = key[:min(limits)]
        return key

    @classmethod
    def track(cls, item, request, permissions):
        pass


class PdfEditor(FileEditor):
    def __init__(self):
        super(PdfEditor, self).__init__()
        self.name = "pdf"
        self.extensions = [".pdf"]
        self.thumbnail = "blocks/thumbnails/file.html"

    @classmethod
    def show(cls, item, request):
        item_rep = item_reps.FileRepresentation(item)
        context = Context({'item_rep': item_rep})
        return render(request, "files/pdf.html", context)
