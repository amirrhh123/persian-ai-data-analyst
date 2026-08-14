from typing import Any, Dict, List


class MultiIntentDetector:
    PERSIAN_CONJUNCTIONS = [" و ", " یا ", " هم ", " همچنین ", " علاوه بر "]

    SALARY_BASE_PHRASES = [
        "حقوق پایه",
        "پایه حقوق",
        "حقوق مبنا",
        "مزد پایه",
    ]
    EDUCATION_GRADE_CONTEXT = [
        "دانش‌آموز",
        "دانش آموز",
        "تحصیلی",
        "کلاس",
        "پایه دهم",
        "پایه یازدهم",
        "پایه دوازدهم",
        "مدرسه",
    ]

    DOMAIN_KEYWORDS = {
        "student": ["دانش‌آموز", "دانش آموز", "ثبت نام", "پایه"],
        "school": ["مدرسه", "مدارس", "دبیرستان", "دبستان", "هنرستان"],
        "employee": ["کارمند", "کارکن", "کارکنان", "مدیر", "دبیر"],
        "salary": ["حقوق", "مزایا", "پرداخت", "دستمزد", "سنوات پرداخت", "مبلغ سنوات"],
        "organization": ["واحد سازمانی", "سازمان", "استان", "منطقه"],
        "ranking": ["ارتقا", "رتبه", "درخواست"],
        "retirement": ["بازنشسته", "بازنشستگی", "سنوات خدمت", "سابقه خدمت"],
    }

    DOMAIN_NAMES_FA = {
        "student": "دانش‌آموزان",
        "school": "مدارس",
        "employee": "کارکنان",
        "salary": "حقوق",
        "organization": "واحدهای سازمانی",
        "ranking": "ارتقای رتبه",
        "retirement": "بازنشستگی",
    }

    def detect(self, question: str) -> Dict[str, Any]:
        has_conjunction = any(conj in question for conj in self.PERSIAN_CONJUNCTIONS)
        detected_domains = self._detect_domains(question)

        if not has_conjunction:
            return self._single_intent_result(detected_domains)

        if len(detected_domains) > 1:
            intents = []
            for domain in detected_domains:
                for keyword in self.DOMAIN_KEYWORDS[domain]:
                    if keyword in question:
                        intents.append({"group": domain, "request": keyword})
                        break

            composability = self._composability(question, detected_domains)
            domain_names = [self.DOMAIN_NAMES_FA.get(d, d) for d in detected_domains]

            return {
                "multi_intent": True,
                "detected_intents": intents,
                "needs_clarification": not composability["is_composable"],
                "clarification_question": None
                if composability["is_composable"]
                else "آیا می‌خواهید اطلاعات مربوط به "
                + " و ".join(domain_names)
                + " را به‌صورت جداگانه دریافت کنید؟",
                "is_composable": composability["is_composable"],
                "shared_grouping_dimension": composability["shared_grouping_dimension"],
                "detected_entities": detected_domains,
                "decomposition_reason": composability["decomposition_reason"],
            }

        return self._single_intent_result(detected_domains)

    def _single_intent_result(self, detected_domains: List[str]) -> Dict[str, Any]:
        return {
            "multi_intent": False,
            "detected_intents": [],
            "needs_clarification": False,
            "clarification_question": None,
            "is_composable": False,
            "shared_grouping_dimension": "",
            "detected_entities": detected_domains,
            "decomposition_reason": None,
        }

    def _detect_domains(self, question: str) -> List[str]:
        salary_base_context = any(phrase in question for phrase in self.SALARY_BASE_PHRASES)
        education_grade_context = any(phrase in question for phrase in self.EDUCATION_GRADE_CONTEXT)
        detected = []

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if keyword not in question:
                    continue
                if domain == "student" and keyword == "پایه" and salary_base_context and not education_grade_context:
                    continue
                detected.append(domain)
                break

        return detected

    def _grouping_dimension(self, question: str) -> str:
        if "هر استان" in question or "به تفکیک استان" in question:
            return "province"
        if "هر منطقه" in question or "به تفکیک منطقه" in question:
            return "city"
        return ""

    def _composability(self, question: str, detected_domains: List[str]) -> Dict[str, Any]:
        grouping = self._grouping_dimension(question)
        if not grouping:
            return {
                "is_composable": False,
                "shared_grouping_dimension": "",
                "decomposition_reason": "No explicit shared grouping dimension",
            }

        if any(term in question for term in ["بیشترین", "بالاترین", "کمترین"]):
            return {
                "is_composable": False,
                "shared_grouping_dimension": grouping,
                "decomposition_reason": "Independent sort or limit request",
            }

        domains = set(detected_domains)
        approved = (
            {"employee", "student"}.issubset(domains)
            or {"school", "student"}.issubset(domains)
            or {"student", "organization"}.issubset(domains)
        )
        if approved:
            return {
                "is_composable": True,
                "shared_grouping_dimension": grouping,
                "decomposition_reason": None,
            }

        return {
            "is_composable": False,
            "shared_grouping_dimension": grouping,
            "decomposition_reason": "No approved one-query composition for detected entities",
        }


multi_intent_detector = MultiIntentDetector()
