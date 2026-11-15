# -*- coding: utf-8 -*-
"""灵灵核心逻辑的单元测试（不弹窗、不联网）。"""
import os
import random
import sys
import tempfile
import time
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ling import behavior, config, llm, memory, mood, outfits, paths, persona, wardrobe  # noqa: E402


class TestMood(unittest.TestCase):
    def test_parse_removes_marker(self):
        text, emo = mood.parse('好呀～<mood:开心>')
        self.assertEqual(text, '好呀～')
        self.assertEqual(emo, '开心')

    def test_parse_bracket_forms(self):
        for raw in ('嗯呢 [[mood:害羞]]', '嗯呢【情绪：害羞】', '嗯呢<情绪:害羞>'):
            text, emo = mood.parse(raw)
            self.assertNotIn('mood', text)
            self.assertNotIn('情绪', text)
            self.assertEqual(emo, '害羞')

    def test_guess_fallback(self):
        self.assertEqual(mood.guess('哼，笨蛋'), '生气')
        self.assertEqual(mood.guess('让我想想…'), '思考')
        self.assertIn(mood.guess(''), mood.EMOTIONS)

    def test_every_emotion_has_act(self):
        for emo in mood.EMOTIONS:
            act = mood.act_for(emo)
            self.assertIn('row', act)
            self.assertGreaterEqual(act['row'], 0)
            self.assertLessEqual(act['row'], 8)


TMP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_tmp')


def tmp_dir():
    """测试用目录：放工作区里，用普通 makedirs（mkdtemp 的 0700 目录在受限环境下不可写）。"""
    os.makedirs(TMP_ROOT, exist_ok=True)
    d = os.path.join(TMP_ROOT, 'case_%s' % uuid.uuid4().hex[:8])
    os.makedirs(d, exist_ok=True)
    return d


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tmp_dir()
        self.mem = memory.Memory(os.path.join(self.tmp, 'memory.json'))

    def test_add_and_persist(self):
        self.mem.add('用户在做一个桌宠项目', 0.9)
        self.mem.save()
        again = memory.Memory(os.path.join(self.tmp, 'memory.json'))
        self.assertEqual(len(again.facts), 1)

    def test_dedupe(self):
        self.mem.add('喜欢猫', 0.5)
        self.mem.add('喜欢猫', 0.9)
        self.assertEqual(len(self.mem.facts), 1)
        self.assertAlmostEqual(self.mem.facts[0]['importance'], 0.9)

    def test_search_hits_topic(self):
        self.mem.add('用户在做桌宠项目，用的是 tkinter', 0.8)
        self.mem.add('用户喜欢喝美式咖啡', 0.6)
        hits = self.mem.search('桌宠做到哪了', 2)
        self.assertTrue(hits)
        self.assertIn('桌宠', hits[0])

    def test_top_by_importance(self):
        self.mem.add('随口一句不重要的事', 0.2)
        self.mem.add('用户是产品经理，在做桌宠', 0.95)
        self.assertEqual(self.mem.top(1), ['用户是产品经理，在做桌宠'])

    def test_short_text_ignored(self):
        self.assertFalse(self.mem.add('嗯', 0.9))

    def test_parse_extracted(self):
        raw = '```json\n[{"text":"用户是产品经理","importance":0.9}]\n```'
        facts = memory.parse_extracted(raw)
        self.assertEqual(facts[0]['text'], '用户是产品经理')
        self.assertEqual(memory.parse_extracted('抱歉我不会'), [])


class TestRoamer(unittest.TestCase):
    def _roamer(self, t=1000.0, seed=1):
        clock = {'t': t}
        r = behavior.Roamer(bounds=lambda: (300, 200, 320, 300, 1920, 1080),
                            now=lambda: clock['t'], rng=random.Random(seed))
        return r, clock

    def test_first_decision_comes_later(self):
        r, clock = self._roamer()
        clock['t'] += 1
        self.assertIsNone(r.tick())

    def test_walk_plan_within_screen(self):
        r, clock = self._roamer()
        clock['t'] += 60
        action = r.tick()
        self.assertIsNotNone(action)
        if action['type'] == 'walk':
            self.assertLessEqual(abs(action['dx']), 400)
            self.assertGreater(action['ms'], 0)
            self.assertIn(action['row'], (1, 2))
            r.end_walk()
            self.assertEqual(r.state, 'idle')

    def test_sleep_after_ten_minutes(self):
        r, clock = self._roamer()
        clock['t'] += behavior.Roamer.SLEEP_AFTER + 1
        self.assertEqual(r.tick()['type'], 'sleep')
        self.assertTrue(r.sleeping)
        self.assertTrue(r.touch())
        self.assertFalse(r.sleeping)

    def test_busy_blocks_walk(self):
        r, clock = self._roamer()
        clock['t'] += 60
        self.assertIsNone(r.tick(busy=True))

    def test_sleep_respects_busy(self):
        r, clock = self._roamer()
        clock['t'] += behavior.Roamer.SLEEP_AFTER + 1
        self.assertIsNone(r.tick(busy=True))


class TestLLM(unittest.TestCase):
    def test_endpoint_variants(self):
        self.assertEqual(llm.endpoint('https://api.deepseek.com'),
                         'https://api.deepseek.com/v1/chat/completions')
        self.assertEqual(llm.endpoint('https://api.openai.com/v1'),
                         'https://api.openai.com/v1/chat/completions')
        self.assertEqual(llm.endpoint('http://127.0.0.1:11434/v1'),
                         'http://127.0.0.1:11434/v1/chat/completions')

    def test_ready_rules(self):
        self.assertFalse(llm.ready({'provider': 'deepseek', 'api_key': ''}))
        self.assertTrue(llm.ready({'provider': 'deepseek', 'api_key': 'sk-x'}))
        self.assertTrue(llm.ready({'provider': 'ollama', 'api_key': ''}))

    def test_resolve_falls_back_to_preset(self):
        provider, base, model, key = llm.resolve({'provider': 'ollama'})
        self.assertEqual(provider, 'ollama')
        self.assertIn('11434', base)
        self.assertTrue(model)

    def test_friendly_error(self):
        self.assertIn('钥匙', llm.friendly_error(401))
        self.assertIn('404', llm.friendly_error(404))


class TestPersona(unittest.TestCase):
    def test_time_context(self):
        import datetime
        now = datetime.datetime(2026, 11, 15, 23, 30)
        ctx = persona.time_context(now=now)
        self.assertIn('2026', ctx)
        self.assertIn('23:30', ctx)
        self.assertIn('深夜', ctx)

    def test_system_prompt_includes_facts(self):
        p = persona.load()
        prompt = persona.system_prompt(p, facts=['用户在写桌宠'], last_talk_at=time.time() - 7200)
        self.assertIn('用户在写桌宠', prompt)
        self.assertIn('小时', prompt)
        self.assertIn('mood', prompt)


class TestConfig(unittest.TestCase):
    def test_merge_keeps_defaults(self):
        tmp = tmp_dir()
        old = config.SETTINGS_PATH
        config.SETTINGS_PATH = os.path.join(tmp, 'settings.json')
        try:
            cfg = config.load()
            self.assertIn('llm', cfg)
            self.assertIn('provider', cfg['llm'])
            cfg['llm']['api_key'] = 'sk-1'
            config.save(cfg)
            again = config.load()
            self.assertEqual(again['llm']['api_key'], 'sk-1')
            self.assertIn('roam', again)
        finally:
            config.SETTINGS_PATH = old

class TestOutfits(unittest.TestCase):
    def test_unknown_falls_back(self):
        self.assertFalse(outfits.exists('nope'))
        self.assertIsNone(outfits.pack_dir('nope'))
        self.assertEqual(outfits.name_of('nope'), 'nope')   # 素材包直接用目录名

    def test_available_includes_builtin(self):
        ids = outfits.available()
        for key in outfits.OUTFITS:
            self.assertIn(key, ids)

    def test_recolor_changes_pixels(self):
        from PIL import Image
        im = Image.new('RGBA', (8, 8), (70, 70, 70, 255))     # 暗灰 = 裙子
        out = outfits.recolor(im, 'wine')
        self.assertNotEqual(out.getpixel((0, 0))[:3], (70, 70, 70))

    def test_classic_unchanged(self):
        from PIL import Image
        im = Image.new('RGBA', (8, 8), (70, 70, 70, 255))
        self.assertIs(outfits.recolor(im, 'classic'), im)

    def test_bright_skin_kept(self):
        from PIL import Image
        im = Image.new('RGBA', (4, 4), (240, 225, 205, 255))  # 亮肤色不该被染
        out = outfits.recolor(im, 'navy')
        self.assertEqual(out.getpixel((0, 0))[:3], (240, 225, 205))


class TestWardrobe(unittest.TestCase):
    def _wardrobe(self, t=1_000_000.0):
        clock = {'t': t}
        w = wardrobe.Wardrobe(now=lambda: clock['t'])
        return w, clock

    def test_night_outfit(self):
        import datetime
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 11, 15, 23, 0)), 'mist')
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 11, 15, 3, 0)), 'mist')

    def test_season_outfit(self):
        import datetime
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 1, 10, 12, 0)), 'navy')
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 4, 10, 12, 0)), 'forest')
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 7, 10, 12, 0)), 'cream')
        self.assertEqual(wardrobe.auto_outfit(datetime.datetime(2026, 10, 10, 12, 0)), 'wine')

    def test_manual_lock_two_hours(self):
        w, clock = self._wardrobe()
        w.set_manual('wine')
        self.assertEqual(w.resolve(__import__('datetime').datetime(2026, 7, 10, 12, 0)), 'wine')
        clock['t'] += wardrobe.MANUAL_LOCK_HOURS * 3600 + 1
        self.assertEqual(w.resolve(__import__('datetime').datetime(2026, 7, 10, 12, 0)), 'cream')

    def test_auto_off_uses_manual(self):
        w, clock = self._wardrobe()
        w.set_manual('forest')
        w.auto = False
        self.assertEqual(w.resolve(), 'forest')

    def test_tick_reports_change(self):
        w, clock = self._wardrobe()
        w.remember('classic')
        target, changed = w.tick(__import__('datetime').datetime(2026, 7, 10, 12, 0))
        self.assertEqual(target, 'cream')
        self.assertTrue(changed)
        w.remember(target)
        _, changed2 = w.tick(__import__('datetime').datetime(2026, 7, 10, 12, 0))
        self.assertFalse(changed2)

class TestVision(unittest.TestCase):
    def test_private_titles(self):
        from ling import vision
        self.assertTrue(vision.is_private('中国银行 - 个人网银'))
        self.assertTrue(vision.is_private('验证码'))
        self.assertTrue(vision.is_private('1Password'))
        self.assertFalse(vision.is_private('Visual Studio Code'))
        self.assertFalse(vision.is_private(''))

    def test_grab_b64(self):
        from ling import vision
        try:
            b64 = vision.grab_b64(360)
        except Exception:
            self.skipTest('当前会话截不了屏')
        self.assertTrue(b64)
        import base64
        import io as _io
        from PIL import Image
        im = Image.open(_io.BytesIO(base64.b64decode(b64)))
        self.assertLessEqual(im.width, 360)

    def test_vision_requires_config(self):
        from ling import llm
        with self.assertRaises(llm.LLMError):
            llm.complete_vision({'provider': 'deepseek', 'api_key': ''}, '', '看看', 'AAAA')

class TestOfflineReply(unittest.TestCase):
    def test_identity_questions(self):
        from ling import paths
        from ling.pet import offline_reply
        lines = paths.read_json(paths.data_path('lines.json'), {})
        self.assertIn('灵灵', offline_reply(lines, '你是谁呀'))
        self.assertIn('灵灵', offline_reply(lines, '你叫什么名字'))
        self.assertTrue(offline_reply(lines, '在干嘛'))

    def test_greeting_and_bye(self):
        from ling import paths
        from ling.pet import offline_reply
        lines = paths.read_json(paths.data_path('lines.json'), {})
        self.assertTrue(len(offline_reply(lines, '你好')) > 0)
        self.assertTrue(len(offline_reply(lines, '晚安')) > 0)

    def test_unknown_falls_back_to_lines(self):
        from ling import paths
        from ling.pet import offline_reply
        lines = paths.read_json(paths.data_path('lines.json'), {})
        reply = offline_reply(lines, '今天纳斯达克怎么样')
        self.assertTrue(reply)
        self.assertNotIn('纳斯达克', reply)

    def test_roam_default_off(self):
        from ling import config
        self.assertFalse(config.DEFAULTS['roam'])
        self.assertFalse(config.DEFAULTS['roam_explicit'])


if __name__ == '__main__':
    unittest.main(verbosity=2)