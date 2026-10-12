"""Imagens de apoio são cenas distintas e não substituem o arquivo anterior."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from leonida import motion,post,render


class VisualsBuildTests(unittest.TestCase):
    def setUp(self):
        cache=Path(__file__).resolve().parents[1]/'.cache/tests'
        cache.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='visuals-',dir=cache)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.data={'id':'visual-fixture','date':'2026-10-12','image':'cover.jpg','foto_limpa':False,
                   'video_segundos':45,'tag':'analise','cta':False,
                   'visuals':[{'image':'first.jpg','credit':'Fixture','label':'Ilustração','text':'Uma informação revisada.'},
                              {'image':'second.jpg','credit':'Fixture','label':'Ilustração'},
                              {'image':'first.jpg','credit':'Fixture'}, {'image':'cover.jpg'}],
                   'pt':{'headline':'Título de teste','caption':'Texto de teste'}}

    def test_distinct_photos_are_rendered_and_the_video_uses_bounded_timing(self):
        cover=render.Render(Image.new('RGB',(32,48),'red'),[render.Layer('bg',Image.new('RGBA',(32,48),'red'))],{'kind':'cover'})
        def photograph(*args,**kwargs):
            color='green' if args[2]=='first.jpg' else 'blue'
            photo=Image.new('RGBA',(32,48),color)
            return render.Render(photo.convert('RGB'),[render.Layer('bg',photo)],{'kind':'foto'})
        def encode(scenes,target_file,**kwargs):
            self.assertEqual([s.kind for s in scenes],['cover','foto','foto'])
            self.assertEqual(kwargs['max_scene_seconds'],7)
            self.assertEqual(kwargs['target'],45)
            target_file.parent.mkdir(exist_ok=True)
            target_file.write_bytes(b'test export')
            return target_file
        with patch.object(post,'OUT_DIR',self.root),patch.object(post,'load',return_value=(self.data,self.root)), \
             patch.object(render,'cover',return_value=cover),patch.object(render,'slide_foto',side_effect=photograph) as photos, \
             patch('leonida.publish.cfg',return_value={'formato':'video'}),patch('leonida.publish.export_jpegs'), \
             patch.object(motion,'build',side_effect=encode):
            output=post.build('visual-fixture',video=False,estilo='v2',log=lambda _:None)
        self.assertEqual(photos.call_count,2)
        self.assertEqual(photos.call_args_list[0].kwargs['label'],'Ilustração')
        self.assertEqual(photos.call_args_list[0].kwargs['context'],'Uma informação revisada.')
        manifest=json.loads((output/'post.json').read_text(encoding='utf-8'))
        self.assertEqual([i['image'] for i in manifest['visuals']],['first.jpg','second.jpg'])
        self.assertTrue((output/'br/02_imagem-apoio.png').is_file())
        self.assertTrue((output/'br/03_imagem-apoio.png').is_file())

    def test_malformed_visuals_fail_before_replacing_existing_delivery(self):
        output=self.root/'2026-10-12/visual-fixture'
        output.mkdir(parents=True)
        old=output/'video.mp4';old.write_bytes(b'old export')
        for visuals in ('url', [None], [{'image':False}], [{'image':'x','label':[]}], [{'image':'x'}]*7):
            with self.subTest(visuals=visuals),patch.object(post,'OUT_DIR',self.root), \
                 patch.object(post,'load',return_value=({**self.data,'visuals':visuals},self.root)):
                with self.assertRaises(ValueError):
                    post.build('visual-fixture',video=False,estilo='v2',log=lambda _:None)
                self.assertEqual(old.read_bytes(),b'old export')


if __name__=='__main__':
    unittest.main()
