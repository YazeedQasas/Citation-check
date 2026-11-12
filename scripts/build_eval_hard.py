"""Build the HARD stress set (data/eval_hard/): subtle contradictions, heavy paraphrase, near-miss IDs,
awkward formatting (line breaks inside a citation, diacritics, plural articles), boundary cases.

Same format as data/eval/ (see build_eval_set.py). Gold statuses are relative to data/corpus/corpus.json.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "eval_hard"


def g(kind, id, status, lang="ar"):
    return {"kind": kind, "id": id, "expected_status": status, "lang": lang}


DRAFTS = {
    "H01.txt": [
        ("المحكمة: بعد الاطلاع على الأوراق وسماع الدفوع، وحيث إن النزاع يتعلق بعقد توريد بين شركتين تجاريتين.", None),
        ("وقد دفع المدعى عليه بأن المادة (40) من قانون التجارة رقم (63) لسنة 2009 تقضي بتقادم الدعاوى التجارية بمرور ثلاث سنوات، وهو دفع غير سديد في رأي المحكمة.", g("statute", "S:63/2009:40", "CONTRADICTS")),
        ("لذلك قررت المحكمة النظر في موضوع الدفع.", None),
    ],
    "H02.txt": [
        ("المحكمة: وحيث إن العامل أُنهيت خدماته بعد ثماني سنوات من العمل لدى المدعى عليها.", None),
        ("ورأى وكيل الشركة أن المادة (31) من قانون العمل رقم (8) لسنة 2013 لا تشترط لإنهاء العقد غير محدد المدة سوى إشعار شفهي قبل خمسة عشر يوماً.", g("statute", "S:8/2013:31", "CONTRADICTS")),
        ("وذهب وكيل العامل إلى أن محكمة النقض قررت في القرار رقم (912) لسنة 2014 أن الفصل التعسفي لا يوجب التعويض في العقود غير محددة المدة.", g("cassation", "C:912/2014", "CONTRADICTS")),
        ("وأضاف أن المادة (24) من قانون العمل رقم (8) لسنة 2013 تلزم صاحب العمل بمنح العامل مكافأة نهاية الخدمة.", g("statute", "S:8/2013:24", "NOT_FOUND")),
        ("لذلك قررت المحكمة تكليف الطرفين بتقديم بيناتهما.", None),
    ],
    "H03.txt": [
        ("المحكمة: بعد المداولة، وحيث إن المستأجر تخلف عن دفع الأجرة لثلاثة أشهر متتالية.", None),
        ("وحيث إن المستأجر ملزم بتسديد الأجرة في الآجال التي اتفق عليها الطرفان، وبحسب المادة (14) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 فإنها تستحق في بداية كل شهر إذا لم يوجد اتفاق، فإن تخلفه يعد إخلالاً.", g("statute", "S:15/2015:14", "CONTRADICTS")),
        ("وقد جرى قضاء محكمة النقض في القرار رقم (87) لسنة 2018 على أن الإنذار الكتابي لازم قبل طلب الإخلاء، وأن علم المستأجر بالمخالفة لا يقوم مقامه.", g("cassation", "C:87/2018", "SUPPORTED")),
        ("وقد ورد في المذكرة قرار رقم (87) لسنة 2019 لمحكمة النقض بخلاف ذلك، ولم تقف المحكمة عليه.", g("cassation", "C:87/2019", "NOT_FOUND")),
        ("وبالمقابل، فإن الدعاوى المتعلقة بالالتزامات التجارية لا تسمع بعد مضي خمس سنوات إلا إذا نص القانون على مدة أقصر، وذلك عملاً بالمادة (40)\nمن قانون التجارة رقم (63)\nلسنة 2009 كما تقدم.", g("statute", "S:63/2009:40", "SUPPORTED")),
        ("لذلك قررت المحكمة رد الدعوى.", None),
    ],
    "H04.txt": [
        ("المحكمة: وحيث إن الاستئناف قُدّم بعد وفاة أحد المستأنف عليهم أثناء سريان الميعاد.", None),
        ("وعملاً بأحكام المادتين (٢٣) و(٢٣ مكرر) من قانون أصول المحاكمات رقم (٤١) لسنة ٢٠٠٨ يمتد الميعاد ثلاثين يوماً ويوقف إذا توفي أحد الخصوم أو فقد أهليته إلى حين تبليغ الورثة.", g("statute", "S:41/2008:23", "SUPPORTED")),
        ("وعملاً بأحكام المادتين (٢٣) و(٢٣ مكرر) من قانون أصول المحاكمات رقم (٤١) لسنة ٢٠٠٨ يمتد الميعاد ثلاثين يوماً ويوقف إذا توفي أحد الخصوم أو فقد أهليته إلى حين تبليغ الورثة.", g("statute", "S:41/2008:23bis", "SUPPORTED")),
        ("كما أن المادة (٢٣ مكرر (أ)) من القانون ذاته تمدد الميعاد في حالة القوة القاهرة.", g("statute", "S:41/2008:23bis-a", "NOT_FOUND")),
        ("وقد قضت محكمة النقض بأن إقرار الخصم في دعوى أخرى لا يُعد إقراراً قضائياً بل دليلاً كتابياً تقدره المحكمة (القرار رقم ٤٥٦ لسنة ٢٠١٥).", g("cassation", "C:456/2015", "SUPPORTED")),
        ("لذلك قررت المحكمة قبول الاستئناف شكلاً.", None),
    ],
    "H05.txt": [
        ("المحكمة: وحيث إن النزاع يتعلق بدين ثابت بإقرار.", None),
        ("عَمَلاً بِأَحْكَامِ الْمَادَّةِ (١٥) مِنْ قَانُونِ الْبَيِّنَاتِ رَقْمِ (٧٧) لِسَنَةِ ٢٠١١ فَإِنَّ الْإِقْرَارَ الْقَضَائِيَّ حُجَّةٌ عَلَى الْمُقِرِّ وَعَلَى غَيْرِهِ.", g("statute", "S:77/2011:15", "CONTRADICTS")),
        ("Commercial claims become time-barred after five years under Article 40 of Commercial Law No. 63 of 2009, as the defendant correctly noted.", g("statute", "S:63/2009:40", "SUPPORTED", "en")),
        ("وقد جاء في قرار محكمة النقض رقم (456) لسنة 2016 أن الإقرار في دعوى أخرى حجة قاطعة.", g("cassation", "C:456/2016", "NOT_FOUND")),
        ("وقد قررت محكمة النقض في القرار رقم (2210) لسنة 2019 أنه ليس لمحكمة الموضوع سلطة تقدير أقوال الشهود.", g("cassation", "C:2210/2019", "CONTRADICTS")),
        ("وفي الحكم المطعون فيه أن الطعن بالاستئناف بعد فوات الميعاد يسقط الحق فيه وللمحكمة أن تقضي بذلك دون طلب من الخصم، وهذا ما قررته محكمة النقض في القرار رقم (1203) لسنة 2017.", g("cassation", "C:1203/2017", "SUPPORTED")),
        ("لذلك قررت المحكمة الحكم بما تقدم.", None),
    ],
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gold = {"_note": "HARD stress set built by scripts/build_eval_hard.py (subtle contradictions, paraphrase, near-miss IDs, awkward formatting)."}
    for name, paras in DRAFTS.items():
        (OUT / name).write_text("\n\n".join(t for t, _ in paras) + "\n", encoding="utf-8")
        gold[name] = [lab for _, lab in paras if lab]
        ids = [(l["kind"], l["id"]) for l in gold[name]]
        assert len(ids) == len(set(ids)), f"{name}: duplicate gold ID"
    (OUT / "gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = sum(len(v) for k, v in gold.items() if not k.startswith("_"))
    print(f"wrote {len(DRAFTS)} drafts, {n} gold citations -> {OUT}")


if __name__ == "__main__":
    main()
