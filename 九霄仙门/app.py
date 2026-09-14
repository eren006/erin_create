import os, json, random, time, hmac, hashlib, shutil
from datetime import timedelta, date
from functools import wraps
from flask import (Flask, render_template, request, redirect, jsonify,
                   url_for, session as S, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

from game_data import (REALMS, MAX_REALM_INDEX, MAJOR_REALMS, BREAKTHROUGH_CHANCE, BASE_EXP_REALM_MULT,
                        realm_by_index, realm_major_idx,
                        BREAKTHROUGH_STAMINA_COST, BREAKTHROUGH_FAIL_MIND_PENALTY,
                        BREAKTHROUGH_PITY_INCREMENT_PCT, BREAKTHROUGH_PITY_GUARANTEE_STREAK,
                        BREAKTHROUGH_ASSIST_CONTRIBUTION_COST, BREAKTHROUGH_ASSIST_BONUS_PCT,
                        BREAKTHROUGH_ASSIST_MIND_PROTECT, pity_stage_label,
                        MIND_DEMON_TRIGGER_MIND_THRESHOLD, MIND_DEMON_TRIGGER_CHANCE,
                        MIND_DEMON_EVENTS, pick_mind_demon_event,
                        TRIBULATION_FLAVOR, MAJOR_BROADCAST_MIN_IDX, GUARDIAN_TYPES, GUARDIAN_ORDER,
                        DAN_STAMINA_COST, DAN_PITY_GUARANTEE_STREAK, DAN_FAIL_MIND_PENALTY,
                        DAN_WARD_MATERIAL, DAN_WARD_CHANCE_BONUS_PCT, DAN_CORE_MATERIAL, DAN_FORTUNE_MATERIAL,
                        DAN_CORE_EXCHANGE, DAN_WARD_EXCHANGE, DAN_CORE_CONTRIBUTION_COST, DAN_QUALITIES, DAN_QUALITY_ORDER,
                        DAN_UPGRADE_LINGSHI_COST, dan_pity_bonus_pct, dan_natural_chance, DAN_SUCCESS_FLAVORS, DAN_FAIL_FLAVORS,
                        INFANT_STAMINA_COST, INFANT_PITY_GUARANTEE_STREAK, INFANT_TRIBULATION_BASE_CHANCE,
                        INFANT_FAIL_WEAKEN_HOURS, INFANT_FAIL_MIND_PENALTY, INFANT_GATHER_COST,
                        INFANT_WARD_MATERIAL, INFANT_WARD_CHANCE_BONUS_PCT, INFANT_CORE_MATERIAL,
                        INFANT_FORTUNE_MATERIAL, INFANT_CORE_EXCHANGE, INFANT_WARD_EXCHANGE,
                        INFANT_CORE_CONTRIBUTION_COST,
                        INFANT_AGILITY_CHANCE_PER_POINT, INFANT_DEFENSE_MIND_MITIGATION_PER_POINT,
                        INFANT_DEFENSE_MIND_MITIGATION_CAP_PCT, INFANT_ARTIFACT_CORE_CHANCE_PER_LEVEL,
                        INFANT_TRIAL_BOLD_MIND_COST, INFANT_TRIAL_BUFF_CHANCE_BONUS_PCT, infant_pity_bonus_pct,
                        INFANT_RECOVER_LINGSHI_COST, INFANT_SUCCESS_FLAVORS, INFANT_FAIL_FLAVORS,
                        SHEN_STAMINA_COST, SHEN_PITY_GUARANTEE_STREAK, SHEN_FAIL_MIND_PENALTY,
                        SHEN_WARD_MATERIAL, SHEN_WARD_CHANCE_BONUS_PCT, SHEN_CORE_MATERIAL, SHEN_GATE_MATERIAL,
                        SHEN_CORE_EXCHANGE, SHEN_WARD_EXCHANGE, SHEN_QUALITIES, SHEN_QUALITY_ORDER,
                        SHEN_UPGRADE_LINGSHI_COST, shen_pity_bonus_pct, SHEN_SUCCESS_FLAVORS, SHEN_FAIL_FLAVORS,
                        HETI_STAMINA_COST, HETI_PITY_GUARANTEE_STREAK, HETI_TRIBULATION_BASE_CHANCE,
                        HETI_FAIL_WEAKEN_HOURS, HETI_RECOVER_LINGSHI_COST, HETI_FAIL_MIND_PENALTY,
                        HETI_GATHER_COST, HETI_WARD_MATERIAL, HETI_WARD_CHANCE_BONUS_PCT, HETI_CORE_MATERIAL,
                        HETI_CORE_EXCHANGE, HETI_WARD_EXCHANGE,
                        HETI_AGILITY_CHANCE_PER_POINT, HETI_DEFENSE_MIND_MITIGATION_PER_POINT,
                        HETI_DEFENSE_MIND_MITIGATION_CAP_PCT, HETI_ARTIFACT_CORE_CHANCE_PER_LEVEL,
                        HETI_TRIAL_BOLD_MIND_COST, HETI_TRIAL_BUFF_CHANCE_BONUS_PCT, heti_pity_bonus_pct,
                        HETI_CHILD_ADULT_REALM_IDX, HETI_CHILD_ADULT_CHANCE_BONUS_PCT,
                        HETI_CHILD_ADULT_CHANCE_BONUS_MAX_PCT, HETI_LINGZHU_REQUIRED,
                        HETI_LINGZHU_MAX_ENTRIES,
                        HETI_SUCCESS_FLAVORS, HETI_FAIL_FLAVORS,
                        CULTIVATE_FLAVORS,
                        MYSTIC_BEAST_FLEE_FLAVORS, MYSTIC_BEAST_AVOID_FLAVORS,
                        MYSTIC_HERB_WAIT_SUCCESS_FLAVORS, MYSTIC_HERB_WAIT_FAIL_FLAVORS, MYSTIC_HERB_QUICK_FLAVORS,
                        MYSTIC_SATCHEL_OPEN_SUCCESS_FLAVORS, MYSTIC_SATCHEL_OPEN_FAIL_FLAVORS,
                        MYSTIC_SATCHEL_PEEK_SUCCESS_FLAVORS, MYSTIC_SATCHEL_PEEK_FAIL_FLAVORS,
                        MYSTIC_CULTIVATOR_COOPERATE_FLAVORS, MYSTIC_CULTIVATOR_TRADE_FLAVORS,
                        MYSTIC_CULTIVATOR_AVOID_FLAVORS,
                        MYSTIC_FORTUNE_BREAKIN_SUCCESS_FLAVORS, MYSTIC_FORTUNE_BREAKIN_FAIL_FLAVORS,
                        MYSTIC_FORTUNE_SACRIFICE_FLAVORS, MYSTIC_FORTUNE_RETREAT_FLAVORS,
                        RETREAT_DURATION_HOURS, RETREAT_EXP_BASE_PER_HOUR, RETREAT_CONTRIBUTION_PER_HOUR,
                        RETREAT_EARLY_EXIT_MULT,
                        PEAK_TECHNIQUES, peak_technique, PEAK_TECHNIQUES_BY_KEY,
                        technique_chapter_pct,
                        TECHNIQUE_OWN_PEAK_AFFINITY, TECHNIQUE_LEARNED_BASE_AFFINITY,
                        TECHNIQUE_ELEMENT_MATCH_BONUS, technique_affinity_band,
                        TECHNIQUE_MASTERY_MAX, TECHNIQUE_MASTERY_GAIN, TECHNIQUE_MASTERY_EPIPHANY_GAIN,
                        technique_mastery_pct,
                        TECHNIQUE_MASTERY_NEAR_PERFECT_LO, TECHNIQUE_MASTERY_NEAR_PERFECT_HI,
                        TECHNIQUE_MASTERY_NEAR_PERFECT_TEXT, meditation_streak_bonus_pct,
                        TECHNIQUE_INHERITANCE_ROLL_CHANCE, TECHNIQUE_INHERITANCE_ELDER_MULT,
                        TECHNIQUE_DEVIATION_GAIN, TECHNIQUE_DEVIATION_MAX,
                        technique_deviation_exp_penalty_pct,
                        COMBAT_MP_START, COMBAT_BASIC_MP_REGEN, COMBAT_DEFEND_MP_REGEN,
                        COMBAT_DEFEND_DAMAGE_REDUCTION_PCT, COMBAT_ROUND_LIMIT, COMBAT_PURSUIT_ROUND_LIMIT,
                        COMBAT_PURSUIT_DAMAGE_MULT, COMBAT_PURSUIT_REWARD_MULT, COMBAT_STACK_MAX,
                        combat_stats, combat_damage, combat_realm_power, technique_moves, TECHNIQUE_MOVES,
                        SPIRIT_SENSE_UNLOCK_REALM_IDX, spirit_sense, spirit_sense_unlocked,
                        roll_lingjue_text, spirit_sea_stability,
                        reveal_chance, persuade_chance, REVEAL_ROUND1_DAMAGE_REDUCTION_PCT,
                        MONSTERS, encounter_monster_power,
                        INJURY_DURATION_SECONDS, INJURY_HP_PENALTY_PCT, INJURY_STAMINA_PENALTY, INJURY_MIND_PENALTY,
                        CAVE_PEAK_BONUS, CAVE_LOCATION_COMMON, cave_location_bonus,
                        COMPANION_BOND_MIND_GIFT,
                        OFFSPRING_COMPANION_MIN_DAYS, OFFSPRING_CONCEIVE_STAMINA_COST,
                        OFFSPRING_CONCEIVE_CONTRIBUTION_COST, OFFSPRING_CONCEIVE_BASE_CHANCE,
                        OFFSPRING_CONCEIVE_PITY_INCREMENT_PCT, OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK,
                        OFFSPRING_CONCEIVE_COOLDOWN_SECONDS, OFFSPRING_CONCEIVE_DAILY_CAP, OFFSPRING_MAX_GENERATION,
                        OFFSPRING_RENAME_COST,
                        OFFSPRING_MARRY_REALM_IDX, OFFSPRING_REALM_CAP_IDX,
                        OFFSPRING_PASSIVE_EXP_PER_HOUR, OFFSPRING_TEACH_STAMINA_COST,
                        OFFSPRING_TEACH_DAILY_LIMIT, OFFSPRING_TEACH_EXP_RANGE, offspring_stage,
                        OFFSPRING_FRAIL_REALM_MAX, OFFSPRING_FRAIL_WARN_CHANCE, OFFSPRING_FRAIL_DEATH_CHANCE,
                        OFFSPRING_HEAL_CONTRIBUTION_COST, OFFSPRING_NPC_MARRIAGE_ROLL_CHANCE,
                        OFFSPRING_FRAIL_GRACE_HOURS, OFFSPRING_FRAIL_HEAL_LATE_MULT,
                        OFFSPRING_PER_COUPLE_LIFETIME_CAP, MARRIAGE_REVOKE_WINDOW_SECONDS,
                        roll_npc_spouse_name, roll_offspring_spirit_root, roll_offspring_talent,
                        OFFSPRING_PERSONALITIES, OFFSPRING_HOBBIES, roll_offspring_personality,
                        roll_offspring_hobby, offspring_stage_flavor, offspring_archetype,
                        roll_offspring_life_event,
                        MANYUE_ENTRY_LINGSHI_COST, MANYUE_DURATION_SECONDS, MANYUE_PHYSIQUE_GAIN_RANGE,
                        MANYUE_MATERIAL_TIER_WEIGHTS, MANYUE_REWARD_WEIGHTS, ZHUAZHOU_ITEMS,
                        MANYUE_GIFT_ACCESSORIES,
                        CONTRIBUTION_TO_LINGSHI_RATE, LINGSHI_TO_CONTRIBUTION_RATE, LINGSHI_EXCHANGE_DAILY_LIMIT,
                        MATERIAL_TIERS, MATERIAL_LABELS,
                        CAVE_TIERS, CAVE_MAX_TIER_INDEX, cave_tier_info,
                        cave_band_pct, cave_stability_stamina_discount,
                        CAVE_ARRAY_LEVELS, CAVE_ARRAY_MAX_LEVEL, cave_array_info,
                        CAVE_GARDEN_CROPS, CAVE_GARDEN_CROPS_BY_KEY,
                        roll_cave_scenery, roll_cave_name,
                        CAVE_TRAITS, roll_cave_trait,
                        RANKS, MAX_EXAM_TIER, MAX_DISCIPLES_PER_PEAK, PEAK_TRANSFER_CONTRIBUTION_COST,
                        PROMOTION_EXAM_DAILY_LIMIT, CULTIVATE_COOLDOWN_SECONDS,
                        CULTIVATE_BASE_EXP_MIN, CULTIVATE_BASE_EXP_MAX, CULTIVATE_BASE_EXP_AVG,
                        CULTIVATE_DIMINISH_AFTER, CULTIVATE_DIMINISH_MULT, CULTIVATE_DIMINISH_COOLDOWN_MULT,
                        CULTIVATE_DIMINISH_HARD_CAP_EXTRA,
                        MENTOR_EXP_BONUS_PCT, LEADER_PEAK_NAME, ELDER_PEAK_NAMES, NPC_ELDER_PROFILES,
                        pick_npc_elder_profile,
                        rank_by_tier, title_for, ACHIEVEMENTS, DAO_PATHS, DAO_DAILY_CAPS, dao_path_bonus,
                        SPIRIT_ROOTS, SPIRIT_ROOT_ORDER, roll_spirit_root, spirit_root_label,
                        SPIRIT_TEST_COOLDOWN_SECONDS, spirit_test_chance_pct,
                        SPIRIT_TEST_FAIL_FLAVORS, SPIRIT_TEST_SUCCESS_TEXT,
                        SPIRIT_ROOT_ASCENSION_MIN_REALM, SPIRIT_ROOT_ASCENSION_CHANCE, next_spirit_root,
                        roll_spirit_root_elements, next_spirit_root_elements,
                        spirit_root_elements_label, spirit_root_can_use_element,
                        TECHNIQUE_LAYER_MULT_CAP,
                        TALENTS, BLOODLINE_KEYS, INHERITANCE_KEYS, TALENT_AWAKEN_REALM,
                        BLOODLINE_ROLL_CHANCE, INHERITANCE_ROLL_CHANCE, roll_bloodline, talent_stage_pct,
                        IMMORTAL_BONES, IMMORTAL_BONE_ROLL_CHANCE, IMMORTAL_BONE_MEDITATION_KEYS,
                        JIUYOU_BONE_KEYS, JIUYOU_BONE_DROP_CHANCE,
                        SECONDS_PER_YEAR, AGE_SECONDS_PER_YEAR, STARTING_AGE_YEARS, LIFESPAN_BY_MAJOR, ASCEND_ON_EXPIRY_MAJOR_IDX, LIFESPAN_WARNING_PCT,
                        LIFESPAN_FINAL_WARNING_YEARS,
                        ASCENSION_STAMINA_COST, ASCENSION_BASE_CHANCE, ASCENSION_ASSIST_CONTRIBUTION_COST,
                        ASCENSION_ASSIST_BONUS_PCT, ASCENSION_FAIL_MIND_PENALTY, ASCENSION_FLAVOR, CELESTIAL_OFFICES,
                        DACHENG_ASCEND_DEADLINE_SECONDS, DACHENG_ASCEND_WARNING_SECONDS,
                        DACHENG_REACHED_FLAVOR, DACHENG_WARNING_FLAVOR, DACHENG_DEADLINE_DEATH_LABEL,
                        lifespan_cap, game_year_of,
                        INVASION_COOLDOWN_DAYS, INVASION_DURATION_HOURS, INVASION_ATTACK_DAILY_LIMIT,
                        INVASION_PHASE_LABELS, INVASION_PHASE_1_HP_RATIO, INVASION_PHASE_2_HP_RATIO,
                        INVASION_PHASE_3_HP_RATIO, INVASION_ADDS, INVASION_ADD_SHIELD_MULT,
                        INVASION_BACKLASH_CHANCE, INVASION_BACKLASH_MIND_PENALTY,
                        INVASION_BACKLASH_DEFENSE_MITIGATION_PER_POINT, INVASION_BACKLASH_MITIGATION_CAP_PCT,
                        INVASION_EXECUTE_DAMAGE_MULT, INVASION_REWARD_TIERS, INVASION_EXPIRE_REWARD_MULT,
                        INVASION_ACCESSORY_MIN_DAMAGE, INVASION_ACCESSORY_KEY, INVASION_ACCESSORY_TEMPLATE,
                        INVASION_ATTACK_FLAVORS, INVASION_ADD_ATTACK_FLAVORS, INVASION_BACKLASH_FLAVOR,
                        INVASION_DEFEATED_FLAVOR, INVASION_EXPIRED_FLAVOR,
                        STAMINA_CAP, STAMINA_REGEN_PER_HOUR, STAMINA_OVERFLOW_CAP, MIND_STATE_BANDS, mind_state_band,
                        CULTIVATE_METHODS,
                        DAILY_TASKS, DAILY_TASKS_SHOWN, DAILY_TASKS_REQUIRED,
                        DAILY_BONUS_REWARD, DAILY_FULL_BONUS_REWARD,
                        COMMISSIONS, COMMISSION_DIMINISH_AFTER, COMMISSION_DIMINISH_MULT,
                        COMMISSION_DIMINISH_STAMINA_MULT,
                        LABOR_JOBS, LABOR_DURATION_HOURS,
                        LABOR_DIMINISH_AFTER_HOURS, LABOR_DIMINISH_MULT, LABOR_DIMINISH_HARD_CAP_EXTRA_HOURS,
                        XIAXIA_TASKS, XIAXIA_TASKS_BY_KEY, XIAXIA_DAILY_CAP,
                        XIAXIA_EQUIPMENT_TEMPLATES, XIAXIA_EQUIPMENT_DROP_CHANCE, xiaxia_title,
                        random_xiaxia_title_up_text,
                        STORY_ENCOUNTERS, STORY_ENCOUNTERS_BY_KEY, STORY_ENCOUNTER_TRIGGER_CHANCE,
                        SHOP_ITEMS, SHOP_DAILY_LIMIT,
                        BOND_TYPES, BOND_INTERACTIONS, BOND_STAGE_THRESHOLDS,
                        SECT_GOSSIP_CHANCE, SECT_GOSSIP_TRIO_CHANCE, random_gossip_text, random_gossip_text_trio,
                        GIFT_TYPES, GIFT_RARITIES, GIFT_TRAITS, GIFT_SOURCE_LABELS, GIFT_FIND_CHANCES,
                        GIFT_EQUIP_SLOTS, GIFT_EQUIP_ATTACK_BONUS, GIFT_EQUIP_DEFENSE_BONUS,
                        MAIL_DAILY_LIMIT, MAIL_INBOX_DISPLAY_LIMIT,
                        ancestor_label, descendant_label,
                        PEAK_SPECIALTIES, peak_specialty, PET_TYPES, PET_QUALITIES,
                        MENTOR_ZI_POOL, MENTOR_NPC_GIFT_MATERIAL, MENTOR_NPC_GIFT_QTY,
                        PET_BASE_BONUS_PCT, PET_MAX_LEVEL, PET_EXP_PER_LEVEL,
                        PET_TRAIN_STAMINA_COST, PET_TRAIN_DAILY_LIMIT, PET_TRAIN_EXP_RANGE, pet_bonus_pct,
                        PET_ASSIST_CHANCE, PET_MAX_LEVEL_COMBAT_ATTACK_BONUS, PET_MAX_LEVEL_COMBAT_DEFENSE_BONUS,
                        PASTLIFE_UNLOCK_REALM_IDX, PASTLIFE_STAMINA_COST, PASTLIFE_DAILY_LIMIT,
                        PASTLIFE_PROGRESS_RANGE, PASTLIFE_STAGE_THRESHOLD, PASTLIFE_MATERIAL_TIER_WEIGHTS,
                        pastlife_talent_shard_key, PASTLIFE_TALENT_SHARD_CHANCE, PASTLIFE_TALENT_SHARD_COST,
                        PASTLIFE_COMBAT_ATTACK_BONUS, PASTLIFE_COMBAT_DEFENSE_BONUS, PASTLIFE_COMBAT_BUFF_LABEL,
                        PASTLIFE_SHARD_TRADE_MAX_ACTIVE,
                        PASTLIFE_TALENT_REINFORCE_COST, PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS,
                        PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS,
                        TIANDI_JINGHUA_TIERS, TIANDI_STAMINA_BOOST_COST, TIANDI_STAMINA_BOOST_AMOUNT,
                        TIANDI_MYSTIC_EXTRA_SESSION_COST, TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP,
                        TIANDI_STAMINA_BOOST_DAILY_CAP, TIANDI_SHOP_WEAPONS, TIANDI_SHOP_WEAPON_COST,
                        TIANDI_FAKE_BUY_FLAVORS, TIANDI_EASTER_EGG_CHANCE, TIANDI_EASTER_EGG_AMOUNT,
                        TIANDI_EASTER_EGG_FLAVORS,
                        PASTLIFE_DIMENSIONS, PASTLIFE_STAGES,
                        PASTLIFE_DIMENSION_LABELS, PASTLIFE_TAG_LABELS, PASTLIFE_PROGRESS_FLAVORS,
                        PAST_LIFE_FIGURES, pastlife_stage_index, pastlife_candidates, pastlife_offer_options,
                        roll_pet_identity, roll_pet_type, pet_quality, pet_max_level,
                        PET_ROSTER_CAP, PET_HOLDING_HOURS, pet_image_url,
                        PET_ADOPT_STAMINA_COST, PET_ADOPT_DAILY_LIMIT,
                        ALCHEMIST_LEVEL_NAMES, ALCHEMIST_MAX_LEVEL, ALCHEMIST_EXP_ON_SUCCESS,
                        ALCHEMIST_EXP_ON_FAIL, ALCHEMIST_SUCCESS_BONUS_PER_LEVEL, ALCHEMIST_MAX_SUCCESS_RATE,
                        RECIPE_DISCOVER_CHANCE, alchemist_level_name, alchemist_exp_to_next, ALCHEMY_RECIPES,
                        ALCHEMY_DIMINISH_AFTER, ALCHEMY_DIMINISH_MULT, ALCHEMY_RECYCLE_EXP,
                        ELEMENTS, ELEMENT_ORDER, ELEMENT_MUTATIONS, ELEMENT_MUTATION_ROLL_CHANCE,
                        ELEMENT_MUTATION_EXP_BONUS_PCT,
                        roll_element_mutation, element_mutation_label,
                        FORGER_LEVEL_NAMES, FORGER_MAX_LEVEL, FORGER_LEVEL_UP_EXP,
                        FORGER_EXP_ON_SUCCESS, FORGER_EXP_ON_FAIL, forger_level_name, forger_exp_to_next,
                        FORGE_RARITIES, FORGE_RARITY_ORDER, FORGE_CORE_MATERIAL_COST,
                        FORGE_DIMINISH_AFTER, FORGE_DIMINISH_MULT,
                        FORGE_CORE_QUALITY_ORDER, FORGE_CORE_QUALITY_WEIGHTS,
                        FORGE_MASTER_TRINKET, FORGE_MASTER_TRINKET_MATERIAL_COST,
                        MYSTIC_ARTIFACT_CORE_TOP_ZONE, MYSTIC_ARTIFACT_CORE_TOP_CHANCE,
                        FESTIVAL_DURATION_HOURS, FESTIVAL_TYPES, FESTIVAL_TYPES_IMPLEMENTED,
                        PET_SHOW_CATEGORIES, FESTIVAL_PET_SHOW_REWARD, PET_QUALITY_ORDER,
                        KAISHAN_DUTIES, KAISHAN_STAGES, KAISHAN_DUTY_REWARD, KAISHAN_LEADER_REWARD_MULT,
                        KAISHAN_LEADER_SUFFIX, kaishan_duty_line, kaishan_stage_index,
                        KAISHAN_MATERIAL_CHANCE, KAISHAN_MATERIAL_QTY_CAPS, KAISHAN_MATERIAL_TIER_WEIGHTS,
                        KAISHAN_HIGH_MATERIAL_CAP,
                        KAISHAN_DRAW_COOLDOWN_SECONDS,
                        ZHONGQIU_LOCATIONS, ZHONGQIU_ACTIVITIES, ZHONGQIU_AFFINITY_GAIN, ZHONGQIU_REWARD,
                        ZHONGQIU_MOONCAKES, ZHONGQIU_BAKE_STEPS, ZHONGQIU_BAKE_ATTEMPTS_PER_HOUR,
                        ZHONGQIU_BAKE_RANK_REWARDS, ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS,
                        zhongqiu_moon_line, zhongqiu_gift_roll,
                        XINSUI_WISHES, XINSUI_WISH_BLESSINGS, XINSUI_WISH_REWARD,
                        XINSUI_ACTIVITIES, XINSUI_STAGES, XINSUI_ACTIVITY_REWARD, XINSUI_BLESSING_REWARD,
                        xinsui_activity_line, xinsui_stage_index, xinsui_blessing_roll,
                        xinsui_wish_snapshot, xinsui_wish_fulfilled,
                        MARKET_LISTING_DAILY_LIMIT, MARKET_LISTING_MAX_ACTIVE, MARKET_TAX_PCT, MARKET_MIN_PRICE,
                        MYSTIC_DAILY_SESSIONS_MAX, mystic_daily_sessions_max, MYSTIC_ENTRY_STAMINA_COST,
                        MYSTIC_STAMINA_START, MYSTIC_HEAL_USES_MAX,
                        MYSTIC_ESCAPE_CHARMS_START, MYSTIC_DEPTH_MAX, MYSTIC_DEPTH_LABELS, MYSTIC_FAINT_LOSS_PCT,
                        MYSTIC_DEPTH_DANGER_MULT, MYSTIC_HIDDEN_UNLOCK_CHANCE, MYSTIC_ZONES, MYSTIC_ZONES_BY_KEY,
                        MYSTIC_ZONE_FORTUNE_DROP,
                        MYSTIC_COMMON_MATERIAL_KEY, roll_mystic_event_type, MYSTIC_NOTHING_FLAVORS,
                        EQUIPMENT_SLOTS, EQUIPMENT_SLOT_LABELS, EQUIPMENT_PRESET_DEFAULT_LABELS,
                        ARTIFACT_CORE_UNLOCK_REALM_IDX, ARTIFACT_CORE_ORIENTATIONS,
                        ARTIFACT_CORE_EXP_PER_LEVEL,
                        ARTIFACT_CORE_NURTURE_MATERIAL_COST, ARTIFACT_CORE_NURTURE_EXP_GAIN,
                        ARTIFACT_CORE_EQUIPMENT_NURTURE_EXP_GAIN,
                        ARTIFACT_CORE_RARE_NURTURE_MATERIAL_COST, ARTIFACT_CORE_RARE_NURTURE_EXP_GAIN,
                        ARTIFACT_CORE_REFORGE_LINGSHI_COST, ARTIFACT_CORE_REFORGE_LEVEL_PENALTY_PCT,
                        ARTIFACT_REBIRTH_LINGSHI_COST, ARTIFACT_REBIRTH_MATERIAL_COST,
                        ARTIFACT_REBIRTH_LEVEL_PENALTY_PCT, ARTIFACT_CORE_STABLE_UPGRADE_COSTS,
                        ARTIFACT_CORE_QUALITIES, ARTIFACT_CORE_QUALITY_ORDER,
                        artifact_core_stat_bonus, artifact_core_max_level, roll_artifact_core_name,
                        roll_artifact_spirit, artifact_growth_title, roll_dan_name, roll_infant_name,
                        roll_technique_insight, roll_equipment_lore,
                        EQUIPMENT_DROP_TEMPLATES, EQUIPMENT_TEMPLATES_BY_KEY, EQUIPMENT_DECOMPOSE_YIELD,
                        WEAPON_DISCIPLINES, WEAPON_MASTERY_THRESHOLDS, WEAPON_MASTERY_TITLES,
                        weapon_discipline_level, weapon_discipline_bonus,
                        FORGE_GEAR_MATERIAL_COST, EQUIPMENT_BASIC_TEMPLATES,
                        SECT_STARTER_WEAPONS, SECT_STARTER_WEAPON_COST,
                        UNIQUE_EQUIPMENT_ZONES, UNIQUE_EQUIPMENT_DROP_CHANCE, UNIQUE_EQUIPMENT_TEMPLATES,
                        mystic_dodge_chance, mystic_trap_check_chance,
                        MYSTIC_AGILITY_ESCAPE_BONUS_PER_POINT,
                        MATERIAL_SYNTHESIZE_RATIO,
                        MATERIAL_EXCHANGE_ITEMS, MATERIAL_EXCHANGE_ITEMS_BY_KEY, DONATE_RATES,
                        TRAVEL_POINTS_CAP, TRAVEL_POINTS_REGEN_PER_DAY,
                        TRAVEL_DURATIONS, TRAVEL_DURATIONS_BY_KEY,
                        TRAVEL_REGIONS, TRAVEL_REGIONS_BY_KEY,
                        TRAVEL_INSTANT_EVENTS, TRAVEL_CHOICE_EVENTS, TRAVEL_CHOICE_EVENTS_BY_KEY,
                        TRAVEL_THREADS, TRAVEL_LEGENDARY_EVENTS, TRAVEL_LEGENDARY_EVENTS_BY_KEY,
                        TRAVEL_LEGENDARY_FAMILIARITY_REQ,
                        TRAVEL_LEGENDARY_BASE_CHANCE, TRAVEL_LEGENDARY_CHANCE_STEP, TRAVEL_LEGENDARY_CHANCE_CAP,
                        TRAVEL_INSTANT_WEIGHT, TRAVEL_CHOICE_WEIGHT, TRAVEL_DANGER_WEIGHT,
                        TRAVEL_FAMILIARITY_CHOICE_BOOST_THRESHOLD, TRAVEL_FAMILIARITY_CHOICE_BOOST_MULT,
                        TRAVEL_THREAD_STATUS_LABELS, TRAVEL_DANGER_EVENTS, TRAVEL_DANGER_EVENTS_BY_KEY,
                        TRAVEL_RESCUE_WINDOW_SECONDS, TRAVEL_RESCUE_CLAIM_SECONDS,
                        TRAVEL_RESCUE_CALLER_REWARD, TRAVEL_RESCUE_RESCUER_REWARD,
                        TRAVEL_RESCUE_RESCUER_REPEAT_REWARD, TRAVEL_RESCUE_ATTEMPT_CONSOLATION,
                        TRAVEL_RESCUE_POWER_DISCOUNT_PCT,
                        TRAVEL_MINOR_INJURY_HOURS, TRAVEL_MINOR_INJURY_MIND_PENALTY,
                        TRAVEL_MINOR_INJURY_CULTIVATE_MULT, TRAVEL_MINOR_INJURY_COMMISSION_MULT,
                        TRAVEL_MINOR_INJURY_LINGSHI_COST,
                        TRAVEL_DANGER_FIGHT_WIN_EFFECTS, TRAVEL_DANGER_FIGHT_LOSE_MIND_PENALTY,
                        TRAVEL_EQUIPMENT_TEMPLATES, TRAVEL_EQUIPMENT_DROP_CHANCE)

ALCHEMY_RECIPES_BY_KEY = {r['key']: r for r in ALCHEMY_RECIPES}
FORGE_RARITIES_BY_KEY = {r['key']: r for r in FORGE_RARITIES}

DAILY_TASKS_BY_KEY = {t['key']: t for t in DAILY_TASKS}
COMMISSIONS_BY_KEY = {c['key']: c for c in COMMISSIONS}
LABOR_JOBS_BY_KEY = {j['key']: j for j in LABOR_JOBS}
MIND_DEMON_EVENTS_BY_KEY = {e['key']: e for e in MIND_DEMON_EVENTS}
SHOP_ITEMS_BY_KEY = {i['key']: i for i in SHOP_ITEMS}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "jiuxiao_xianmen_secret_2026")
app.permanent_session_lifetime = timedelta(days=30)

@app.template_filter('fmt_ts')
def fmt_ts(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'

DB_PATH     = os.path.join(os.path.dirname(__file__), "jiuxiao.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
ADMIN_USER  = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS  = os.environ.get("ADMIN_PASSWORD", "jiuxiao_admin_888")
SECT_NAME   = '九霄仙门'
SUCCESSION_DELAY_SECONDS = int(os.environ.get("SUCCESSION_DELAY_SECONDS", 6 * 86400))
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN")  # 没配置就直接拒绝 /api/* ,不留一个空字符串就能过的后门
NPC_ELDER_USERNAME = '__npc_elders__'
now_ts      = lambda: int(time.time())
today_str   = lambda: date.today().isoformat()

# ── 数据库 ─────────────────────────────────────────────────────────────────────

def get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
    return db

@app.teardown_appcontext
def close_db(e=None):
    db = getattr(g, '_db', None)
    if db: db.close()

def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    return cur.fetchone() if one else cur.fetchall()

def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    with open(SCHEMA_PATH, encoding='utf-8') as f:
        db.executescript(f.read())
    _ensure_story_columns(db)
    _migrate_legacy_pets(db)
    _migrate_spirit_root_elements(db)
    _migrate_peaks_elder_unique(db)
    db.commit()
    _ensure_admin(db)
    _ensure_sect_config(db)
    _ensure_peaks(db)
    _ensure_npc_elders(db)
    _normalize_real_join_sequences(db)
    _ensure_achievement_defs(db)
    db.close()

def _ensure_story_columns(db):
    """为旧存档补齐个性化叙事字段；只增列，不改动已有数据。"""
    additions = {
        'characters': {
            'pet_appearance': 'TEXT', 'pet_personality': 'TEXT', 'pet_habit': 'TEXT',
            'pet_breeder_name': 'TEXT', 'pet_history': 'TEXT',
            'artifact_core_spirit': 'TEXT', 'dan_name': 'TEXT', 'infant_name': 'TEXT',
            'is_npc': 'INTEGER NOT NULL DEFAULT 0',
            'travel_points': 'INTEGER NOT NULL DEFAULT 2', 'travel_points_ts': 'INTEGER DEFAULT 0',
            'severe_injury_until_ts': 'INTEGER DEFAULT 0',
            'lifespan_warned_realm_idx': 'INTEGER DEFAULT -1',
            'lifespan_final_warned_realm_idx': 'INTEGER DEFAULT -1',
            'dao_path_key': 'TEXT', 'dao_path_chosen_ts': 'INTEGER',
            'xiaxia_fame': 'INTEGER NOT NULL DEFAULT 0',
            'pending_story_key': 'TEXT DEFAULT NULL',
            'equipped_pet_id': 'INTEGER DEFAULT NULL',
            'spirit_root_elements': 'TEXT DEFAULT NULL',
            'labor_job_key': 'TEXT DEFAULT NULL',
            'labor_started_ts': 'INTEGER DEFAULT 0',
            'labor_until_ts': 'INTEGER DEFAULT 0',
            'face_claim': 'TEXT DEFAULT NULL',
            'retreat_notify_sent': 'INTEGER NOT NULL DEFAULT 0',
            'jindan_core_contrib_used': 'INTEGER NOT NULL DEFAULT 0',
            'yuanying_core_contrib_used': 'INTEGER NOT NULL DEFAULT 0',
            'labor_notify_sent': 'INTEGER NOT NULL DEFAULT 0',
            'zi': 'TEXT DEFAULT NULL',
            'death_label': 'TEXT DEFAULT NULL',
            'death_ts': 'INTEGER DEFAULT NULL',
            'incense_count': 'INTEGER NOT NULL DEFAULT 0',
            'pastlife_path_json': 'TEXT DEFAULT NULL',
            'pastlife_progress': 'INTEGER NOT NULL DEFAULT 0',
            'pastlife_key': 'TEXT DEFAULT NULL',
            'pastlife_talent_exchanged': 'INTEGER NOT NULL DEFAULT 0',
            'tiandi_jinghua': 'INTEGER NOT NULL DEFAULT 0',
            'equipped_tassel_gift_id': 'INTEGER DEFAULT NULL',
            'equipped_jade_gift_id': 'INTEGER DEFAULT NULL',
            'talent_reinforce_count': 'INTEGER NOT NULL DEFAULT 0',
            'peak_transferred': 'INTEGER NOT NULL DEFAULT 0',
            'equipped_trinket_key': 'TEXT DEFAULT NULL',
            'celestial_office_key': 'TEXT DEFAULT NULL',
            'ascension_office_choices_json': 'TEXT DEFAULT NULL',
            'dacheng_deadline_ts': 'INTEGER DEFAULT NULL',
            'dacheng_warned': 'INTEGER NOT NULL DEFAULT 0',
            'ascend_ts': 'INTEGER DEFAULT NULL',
            'age_baseline_years': 'INTEGER DEFAULT NULL',
            'age_baseline_ts': 'INTEGER DEFAULT NULL',
        },
        'mail': {'link_url': 'TEXT DEFAULT NULL'},
        'sect_config': {'pastlife_event_ends_ts': 'INTEGER DEFAULT NULL'},
        'character_techniques': {'insight': 'TEXT'},
        'travel_threads': {'last_choice_label': 'TEXT DEFAULT NULL', 'last_result_text': 'TEXT DEFAULT NULL'},
        'character_equipment': {'lore': 'TEXT'},
        'offspring': {'archetype': 'TEXT', 'life_event': 'TEXT',
                      'manyue_status': 'TEXT DEFAULT NULL', 'manyue_started_ts': 'INTEGER DEFAULT NULL',
                      'manyue_result_item_key': 'TEXT DEFAULT NULL', 'manyue_result_guest_id': 'INTEGER DEFAULT NULL'},
        'bonds': {'affinity': 'INTEGER NOT NULL DEFAULT 0'},
        'travel_sessions': {'had_special_event': 'INTEGER NOT NULL DEFAULT 0'},
        'character_region_familiarity': {'legendary_miss_streak': 'INTEGER NOT NULL DEFAULT 0'},
        'travel_rescue_calls': {'claimed_by': 'INTEGER', 'claim_expires_ts': 'INTEGER DEFAULT 0'},
        'chronicle': {'is_major': 'INTEGER NOT NULL DEFAULT 0'},
        'kaishan_participation': {'bonus_material_key': 'TEXT DEFAULT NULL', 'bonus_material_qty': 'INTEGER DEFAULT NULL'},
        'kaishan_draws': {'high_material_qty': 'INTEGER NOT NULL DEFAULT 0'},
        'users': {
            'spirit_test_attempts': 'INTEGER NOT NULL DEFAULT 0',
            'spirit_test_last_ts': 'INTEGER NOT NULL DEFAULT 0',
            'spirit_test_passed': 'INTEGER NOT NULL DEFAULT 0',
        },
    }
    for table, columns in additions.items():
        existing = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    db.execute("""CREATE TABLE IF NOT EXISTS character_weapon_masteries (
        char_id INTEGER NOT NULL, weapon_style TEXT NOT NULL,
        mastery INTEGER NOT NULL DEFAULT 0, updated_ts INTEGER DEFAULT 0,
        PRIMARY KEY (char_id, weapon_style),
        FOREIGN KEY (char_id) REFERENCES characters(id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS bond_interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bond_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
        action_key TEXT NOT NULL, day TEXT NOT NULL, memory_text TEXT NOT NULL,
        affinity_gain INTEGER NOT NULL DEFAULT 0, created_ts INTEGER DEFAULT 0,
        UNIQUE (bond_id, actor_id, day),
        FOREIGN KEY (bond_id) REFERENCES bonds(id),
        FOREIGN KEY (actor_id) REFERENCES characters(id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS manyue_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        offspring_id INTEGER NOT NULL, guest_char_id INTEGER NOT NULL, item_key TEXT NOT NULL,
        reward_kind TEXT NOT NULL, reward_detail TEXT, claimed INTEGER NOT NULL DEFAULT 0,
        created_ts INTEGER NOT NULL,
        UNIQUE(offspring_id, guest_char_id),
        FOREIGN KEY (offspring_id) REFERENCES offspring(id),
        FOREIGN KEY (guest_char_id) REFERENCES characters(id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS pastlife_shard_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        offerer_char_id INTEGER NOT NULL, offer_talent_key TEXT NOT NULL, want_talent_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open', accepted_by_char_id INTEGER,
        created_ts INTEGER NOT NULL, resolved_ts INTEGER,
        FOREIGN KEY (offerer_char_id) REFERENCES characters(id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS bond_gifts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, maker_id INTEGER, owner_id INTEGER NOT NULL,
        recipient_id INTEGER, bond_id INTEGER, gift_type TEXT NOT NULL, gift_name TEXT NOT NULL,
        rarity_key TEXT NOT NULL, trait_key TEXT NOT NULL, source_key TEXT NOT NULL,
        origin_text TEXT NOT NULL, message TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'inventory',
        created_ts INTEGER DEFAULT 0, gifted_ts INTEGER DEFAULT 0, responded_ts INTEGER DEFAULT 0,
        FOREIGN KEY (maker_id) REFERENCES characters(id), FOREIGN KEY (owner_id) REFERENCES characters(id),
        FOREIGN KEY (recipient_id) REFERENCES characters(id), FOREIGN KEY (bond_id) REFERENCES bonds(id))""")
    # 历任掌门:每次继任/夺位开一条新纪录(ended_ts为空=在位中),卸任时补上结束原因——
    # 被挑落的额外记下是被谁打败的,这样"历代掌门"才留得住被夺位者的名字,不会因为后来
    # 掉了rank_tier就从记录里消失(旧的"历代掌门"列表是实时查rank_tier=6,天然做不到这点)。
    db.execute("""CREATE TABLE IF NOT EXISTS leader_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, char_id INTEGER NOT NULL,
        started_ts INTEGER NOT NULL, ended_ts INTEGER, end_reason TEXT,
        defeated_by_char_id INTEGER,
        FOREIGN KEY (char_id) REFERENCES characters(id))""")
    # 建表那一刻如果已经有位在任掌门却还没有在位纪录(老档案升级到这套系统),给TA补一条,
    # 起始时间没法还原,只能用角色创建时间兜底近似。
    if not db.execute("SELECT 1 FROM leader_history LIMIT 1").fetchone():
        incumbent = db.execute("""SELECT characters.id, characters.created_ts FROM peaks
            JOIN characters ON characters.id = peaks.elder_id WHERE peaks.is_leader=1""").fetchone()
        if incumbent:
            db.execute("INSERT INTO leader_history (char_id, started_ts) VALUES (?, ?)",
                       (incumbent[0], incumbent[1]))
    # 年龄增长提速(AGE_SECONDS_PER_YEAR)只应作用在"从现在起"的时间上,不能拿新速率去重算
    # 角色这些年已经攒下的岁数——否则老角色一夜暴增好几岁,寿元瞬间爆表。这里给还没设过
    # 基准的角色,用*旧*速率(SECONDS_PER_YEAR)把"到此刻为止"的年龄冻结成基准,此后的年龄
    # 都是"基准 + (now-基准时间)//AGE_SECONDS_PER_YEAR"——新建角色走 _character_age() 里的
    # 兜底分支,不受此处影响。
    now = now_ts()
    stale = db.execute("SELECT id, created_ts FROM characters WHERE age_baseline_ts IS NULL").fetchall()
    for row in stale:
        baseline_years = STARTING_AGE_YEARS + (now - row[1]) // SECONDS_PER_YEAR
        db.execute("UPDATE characters SET age_baseline_years=?, age_baseline_ts=? WHERE id=?",
                   (baseline_years, now, row[0]))
    db.commit()

def _migrate_spirit_root_elements(db):
    """老存档没有灵根属性,按各自灵根档位数量随机补齐一次;幂等:已经补过的角色(elements非空或天灵根)跳过。"""
    rows = db.execute("""SELECT id, spirit_root FROM characters
                          WHERE spirit_root IS NOT NULL AND spirit_root_elements IS NULL
                          AND spirit_root != 'heaven'""").fetchall()
    for c in rows:
        elements = roll_spirit_root_elements(c['spirit_root'])
        if elements:
            db.execute("UPDATE characters SET spirit_root_elements=? WHERE id=?",
                       (','.join(elements), c['id']))
    db.commit()

def _migrate_peaks_elder_unique(db):
    """老表结构里 elder_id 是 UNIQUE 列,导致"继任掌门后原峰长老身份保留(一人身兼两峰elder_id)"
    这个设计没法落地——SQLite不支持直接删列约束,重建表迁移一次;幂等,迁移过后不会再有这条唯一索引。"""
    has_unique = False
    for idx in db.execute("PRAGMA index_list('peaks')").fetchall():
        if not idx['unique']:
            continue
        cols = [c['name'] for c in db.execute(f"PRAGMA index_info('{idx['name']}')").fetchall()]
        if cols == ['elder_id']:
            has_unique = True
            break
    if not has_unique:
        return
    db.execute("PRAGMA foreign_keys=OFF")
    db.execute("""CREATE TABLE peaks_new (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT UNIQUE NOT NULL,
        is_leader   INTEGER NOT NULL DEFAULT 0,
        elder_id    INTEGER DEFAULT NULL,
        created_ts  INTEGER DEFAULT 0,
        FOREIGN KEY (elder_id) REFERENCES characters(id)
    )""")
    db.execute("INSERT INTO peaks_new (id,name,is_leader,elder_id,created_ts) "
               "SELECT id,name,is_leader,elder_id,created_ts FROM peaks")
    db.execute("DROP TABLE peaks")
    db.execute("ALTER TABLE peaks_new RENAME TO peaks")
    db.execute("PRAGMA foreign_keys=ON")
    db.commit()

def _migrate_legacy_pets(db):
    """把旧版"单宠物字段挂在characters上"的存档一次性搬进character_pets;
    幂等:已经有pets行的角色跳过,不会重复搬。"""
    rows = db.execute("""SELECT * FROM characters WHERE pet_key IS NOT NULL
                          AND id NOT IN (SELECT DISTINCT char_id FROM character_pets)""").fetchall()
    for c in rows:
        cur = db.execute("""INSERT INTO character_pets
            (char_id,pet_key,pet_name,appearance,personality,habit,breeder_name,history,level,exp,bound_ts,location)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'roster')""",
            (c['id'], c['pet_key'], c['pet_name'], c['pet_appearance'], c['pet_personality'], c['pet_habit'],
             c['pet_breeder_name'], c['pet_history'], c['pet_level'], c['pet_exp'], c['pet_bound_ts']))
        db.execute("UPDATE characters SET equipped_pet_id=? WHERE id=?", (cur.lastrowid, c['id']))
    db.commit()

def _ensure_admin(db):
    row = db.execute("SELECT id FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (ADMIN_USER, generate_password_hash(ADMIN_PASS, method='pbkdf2:sha256'),
             '00000000', 'admin', 'approved', now_ts()))
        db.commit()

def _ensure_sect_config(db):
    row = db.execute("SELECT id FROM sect_config WHERE id=1").fetchone()
    if not row:
        ts = now_ts()
        db.execute(
            "INSERT INTO sect_config (id,sect_name,npc_leader_name,founded_ts,succession_target_ts,succession_done) "
            "VALUES (1,?,?,?,?,0)",
            (SECT_NAME, '沈天铭', ts, ts + SUCCESSION_DELAY_SECONDS))
        db.commit()

def _ensure_peaks(db):
    row = db.execute("SELECT id FROM peaks LIMIT 1").fetchone()
    if row:
        return
    ts = now_ts()
    db.execute("INSERT INTO peaks (name,is_leader,elder_id,created_ts) VALUES (?,1,NULL,?)",
               (LEADER_PEAK_NAME, ts))
    for name in ELDER_PEAK_NAMES:
        db.execute("INSERT INTO peaks (name,is_leader,elder_id,created_ts) VALUES (?,0,NULL,?)", (name, ts))
    db.commit()

def _ensure_npc_elders(db):
    """开服头几天不会有真实弟子够格当长老,7座长老峰各配一名NPC长老坐镇,
    免得弟子拜入峰后无人可拜、无师可承;真实弟子日后考核达标即可将其顶替(见 promote_exam 的 is_npc 分支)。
    只在全服从未出现过真实长老时补位一次,避免覆盖真实弟子退位后留下的正常空缺。"""
    real_elder = db.execute("SELECT id FROM characters WHERE rank_tier=5 AND is_npc=0 LIMIT 1").fetchone()
    if real_elder:
        return
    vacant_peaks = db.execute("SELECT * FROM peaks WHERE is_leader=0 AND elder_id IS NULL").fetchall()
    if not vacant_peaks:
        return
    npc_user = db.execute("SELECT id FROM users WHERE username=?", (NPC_ELDER_USERNAME,)).fetchone()
    if npc_user:
        npc_user_id = npc_user['id']
    else:
        db.execute(
            "INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (NPC_ELDER_USERNAME, generate_password_hash(os.urandom(16).hex(), method='pbkdf2:sha256'),
             '00000000', 'npc', 'approved', now_ts()))
        npc_user_id = db.execute("SELECT id FROM users WHERE username=?", (NPC_ELDER_USERNAME,)).fetchone()['id']
    ts = now_ts()
    elder_rank = RANKS[5]
    for peak in vacant_peaks:
        profiles = NPC_ELDER_PROFILES.get(peak['name'])
        if not profiles:
            continue
        profile = random.choice(profiles)
        cur = db.execute(
            "INSERT INTO characters (user_id,name,gender,bio,realm_idx,exp,rank_tier,join_seq,peak_id,"
            "contribution,total_contribution,reputation,is_npc,created_ts) "
            "VALUES (?,?,?,?,?,?,5,?,?,?,?,?,1,?)",
            (npc_user_id, profile['name'], profile['gender'], profile['bio'], profile['realm_idx'],
             REALMS[profile['realm_idx']]['exp'],
             0, peak['id'], elder_rank['contribution_req'], elder_rank['contribution_req'],
             elder_rank['reputation_req'], ts))
        db.execute("UPDATE peaks SET elder_id=? WHERE id=?", (cur.lastrowid, peak['id']))
    db.commit()

def _normalize_real_join_sequences(db):
    """NPC长老不占弟子辈分；真实角色依原入门顺序压缩为1..N。"""
    db.execute("UPDATE characters SET join_seq=0 WHERE is_npc=1 AND join_seq!=0")
    rows = db.execute("""SELECT id FROM characters WHERE is_npc=0
                         ORDER BY CASE WHEN join_seq>0 THEN 0 ELSE 1 END, join_seq, created_ts, id""").fetchall()
    for seq, row in enumerate(rows, 1):
        db.execute("UPDATE characters SET join_seq=? WHERE id=? AND join_seq!=?", (seq, row['id'], seq))
    db.commit()

def _ensure_achievement_defs(db):
    for a in ACHIEVEMENTS:
        db.execute(
            "INSERT INTO achievement_defs (key,name,description,condition_json,reward_json) VALUES (?,?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET name=excluded.name, description=excluded.description, "
            "condition_json=excluded.condition_json, reward_json=excluded.reward_json",
            (a['key'], a['name'], a['description'], json.dumps(a['condition'], ensure_ascii=False),
             json.dumps(a['reward'], ensure_ascii=False)))
    db.commit()

# ── 危险操作:整服重置回初始状态 ────────────────────────────────────────────────
# 重置前先把db文件复制一份留底,再把所有表DROP掉用schema.sql+既有的_ensure_*种子函数重新铺一遍,
# 这样"初始状态"跟这套代码第一次部署时init_db()铺出来的状态完全一致(管理员账号/宗门配置/诸峰/NPC长老都会重新生成),
# 不用另外维护一份"出厂设置"逻辑。

RESET_CONFIRM_PHRASE = '彻底重置九霄仙门'
RESET_LOG_PATH = os.path.join(os.path.dirname(__file__), 'reset_log.txt')

def reset_game_to_initial_state(triggered_by):
    backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    backup_name = f"jiuxiao_before_reset_{time.strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_PATH, os.path.join(backup_dir, backup_name))

    db = get_db()
    db.execute("PRAGMA foreign_keys=OFF")
    tables = [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for t in tables:
        db.execute(f"DROP TABLE IF EXISTS {t}")
    db.commit()
    with open(SCHEMA_PATH, encoding='utf-8') as f:
        db.executescript(f.read())
    _ensure_story_columns(db)
    _migrate_legacy_pets(db)
    _migrate_spirit_root_elements(db)
    db.commit()
    _ensure_admin(db)
    _ensure_sect_config(db)
    _ensure_peaks(db)
    _ensure_npc_elders(db)
    _ensure_achievement_defs(db)
    db.execute("PRAGMA foreign_keys=ON")

    with open(RESET_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} by {triggered_by}: 整服重置,重置前备份={backup_name}\n")
    return backup_name

# ── 登录态 ─────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in S:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if S.get('role') != 'admin':
            flash('无权访问', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return w

def me_character():
    uid = S.get('uid')
    if not uid:
        return None
    row = q("SELECT * FROM characters WHERE user_id=? AND ascended=0 AND deceased=0", (uid,), one=True)
    return dict(row) if row else None

def ensure_character_story(char):
    """按需为新旧角色生成永久叙事身份，同一字段只生成一次。"""
    updates = {}
    mutation = ELEMENT_MUTATIONS.get(char.get('element_mutation')) or {}
    element = mutation.get('element')
    for pet in q("SELECT * FROM character_pets WHERE char_id=? AND (appearance IS NULL OR breeder_name IS NULL)",
                 (char['id'],)):
        pet_updates = {}
        if not pet['appearance']:
            pet_updates['appearance'], pet_updates['personality'], pet_updates['habit'] = roll_pet_identity()
        if not pet['breeder_name']:
            pet_updates['breeder_name'] = char['name']
            pet_updates['history'] = pet['history'] or f"由{char['name']}在紫霄峰收养并亲自培育"
        if pet_updates:
            sets = ','.join(f'{key}=?' for key in pet_updates)
            run(f"UPDATE character_pets SET {sets} WHERE id=?", (*pet_updates.values(), pet['id']))
    if char.get('artifact_core_bound') and not char.get('artifact_core_spirit'):
        updates['artifact_core_spirit'] = roll_artifact_spirit(char.get('artifact_core_orientation'))
    if char.get('dan_quality') and not char.get('dan_name'):
        updates['dan_name'] = roll_dan_name(element, char.get('artifact_core_orientation'))
    if char.get('realm_idx', 0) >= 9 and not char.get('infant_name'):
        updates['infant_name'] = roll_infant_name(element, char.get('artifact_core_orientation'))
    if updates:
        sets = ','.join(f'{key}=?' for key in updates)
        run(f"UPDATE characters SET {sets} WHERE id=?", (*updates.values(), char['id']))
        char.update(updates)
    for row in q("SELECT technique_key FROM character_techniques WHERE char_id=? AND mastery>=80 AND insight IS NULL",
                 (char['id'],)):
        tech = PEAK_TECHNIQUES_BY_KEY.get(row['technique_key'], {})
        run("UPDATE character_techniques SET insight=? WHERE char_id=? AND technique_key=?",
            (roll_technique_insight(tech.get('element')), char['id'], row['technique_key']))
    return char

def log_admin(action, target_type='', target_id=None, detail=''):
    run("INSERT INTO admin_logs (admin_id,target_type,target_id,action,detail,created_ts) VALUES (?,?,?,?,?,?)",
        (S.get('real_admin_uid', S.get('uid')), target_type, target_id, action, detail, now_ts()))

# ── 站内信(兼作通知系统) ─────────────────────────────────────────────────────────

def send_system_mail(char_id, subject, body='', attachment=None, from_label='系统', link_url=None):
    """link_url 只能由系统侧调用方传入(通常是 url_for(...) 拼出来的站内路径),不接受玩家输入,
    mail.html 直接拿去当 href 渲染成按钮——保证不了外部/玩家可控字符串的安全性,别用来传那种。"""
    run("INSERT INTO mail (char_id,from_label,subject,body,attachment_json,link_url,claimed,read,created_ts) "
        "VALUES (?,?,?,?,?,?,0,0,?)",
        (char_id, from_label, subject, body,
         json.dumps(attachment, ensure_ascii=False) if attachment else None, link_url, now_ts()))

def unread_mail_count(char_id):
    return q("SELECT COUNT(*) c FROM mail WHERE char_id=? AND read=0", (char_id,), one=True)['c']

@app.context_processor
def inject_globals():
    char = me_character()
    return {
        'unread_mail_count': unread_mail_count(char['id']) if char else 0,
        'sect_name': SECT_NAME,
        'title_for': title_for,
        'invasion_active': bool(q("SELECT 1 FROM invasions WHERE status='active' AND ends_ts>? LIMIT 1",
                                   (now_ts(),), one=True)),
        'festival_active': bool(q("SELECT 1 FROM festivals WHERE status='active' AND ends_ts>? LIMIT 1",
                                   (now_ts(),), one=True)),
        'rescue_calls_pending': bool(q("""SELECT 1 FROM travel_rescue_calls WHERE status='open' AND expires_ts>?
                                           AND char_id!=? AND (claimed_by IS NULL OR claim_expires_ts<?) LIMIT 1""",
                                        (now_ts(), char['id'] if char else -1, now_ts()), one=True)),
        'story_event_pending': bool(char and char.get('pending_story_key')),
    }

# ── 每日计数器(通用限流基建) ─────────────────────────────────────────────────────

def bump_daily_counter(char_id, key, amount=1):
    day = today_str()
    run("INSERT INTO daily_counters (char_id,counter_key,day,count) VALUES (?,?,?,?) "
        "ON CONFLICT(char_id,counter_key,day) DO UPDATE SET count=count+?", (char_id, key, day, amount, amount))
    return q("SELECT count FROM daily_counters WHERE char_id=? AND counter_key=? AND day=?",
              (char_id, key, day), one=True)['count']

def get_daily_counter(char_id, key):
    row = q("SELECT count FROM daily_counters WHERE char_id=? AND counter_key=? AND day=?",
            (char_id, key, today_str()), one=True)
    return row['count'] if row else 0

def unlocked_dao_paths(char_id):
    return {r['path_key'] for r in q("SELECT path_key FROM character_dao_paths WHERE char_id=? AND unlocked_ts IS NOT NULL",
                                      (char_id,))}

def chosen_dao_path(char_id):
    row = q("SELECT dao_path_key FROM characters WHERE id=?", (char_id,), one=True)
    return row['dao_path_key'] if row and row['dao_path_key'] in DAO_PATHS else None

def add_dao_progress(char_id, path_key, amount=1, daily_cap=None, counter_suffix=None):
    """累计道途进度并在达标时永久解锁；可选每日上限防止低成本重复刷取。
    同一道途若有多个不相干的触发来源(如逍遥道的侠客行/秘境/游历),用 counter_suffix 区分各自的每日上限,
    否则它们会共用一个计数器,导致其中一种活动触发后,当天其余活动全部无法再计入进度。"""
    path = DAO_PATHS.get(path_key)
    if not path:
        return False
    if chosen_dao_path(char_id):
        return False
    if daily_cap is not None:
        counter = f'dao_{path_key}' + (f'_{counter_suffix}' if counter_suffix else '')
        if get_daily_counter(char_id, counter) >= daily_cap:
            return False
        bump_daily_counter(char_id, counter)
    run("""INSERT INTO character_dao_paths(char_id,path_key,progress) VALUES(?,?,?)
           ON CONFLICT(char_id,path_key) DO UPDATE SET progress=MIN(?,progress+?)
           WHERE unlocked_ts IS NULL""", (char_id, path_key, amount, path['target'], amount))
    row = q("SELECT progress,unlocked_ts FROM character_dao_paths WHERE char_id=? AND path_key=?",
            (char_id, path_key), one=True)
    if row and not row['unlocked_ts'] and row['progress'] >= path['target']:
        ts = now_ts()
        run("UPDATE character_dao_paths SET unlocked_ts=? WHERE char_id=? AND path_key=? AND unlocked_ts IS NULL",
            (ts, char_id, path_key))
        send_system_mail(char_id, f"道途候选·{path['label']}",
                         f"你已达成「{path['requirement']}」，获得选择{path['label']}的资格。"
                         f"若正式立道，将获得永久效果：{path['bonus_desc']}。每人只能选择一条，请慎重决定。",
                         from_label='大道感应')
        return True
    return False

def dao_bonus(char_id, bonus_key):
    chosen = chosen_dao_path(char_id)
    return dao_path_bonus({chosen} if chosen else set(), bonus_key)

# ── 奖励发放(通用):reward dict 里 exp / contribution 两个字段可组合使用 ────────────

_REWARD_FIELDS = ('exp', 'contribution', 'lingshi', 'lifespan_years', 'stamina', 'physique', 'mind_state', 'reputation',
                   'xiaxia_fame', 'tiandi_jinghua')

def get_peak_specialty(char):
    """掌门移驻掌门峰后,除了掌门峰自身的四项综合加成,原峰独有的活动资格(收养/炼丹/炼器/秘境加成等)
    仍应保留——跟 _technique_peak_name 同一个"原峰长老之位仍挂其名"的判断方式,只是这里合并的是
    峰属性字典而不是功法。掌门峰没有的key(pet/alchemy/forge/shop_discount_pct/mystic_*)照单全收原峰的值,
    掌门峰自己就有的四项(exp/breakthrough/commission/reputation bonus,含theme/desc展示文案)仍以掌门峰为准。"""
    if not char or not char.get('peak_id'):
        return {}
    row = q("SELECT name FROM peaks WHERE id=?", (char['peak_id'],), one=True)
    if not row:
        return {}
    specialty = peak_specialty(row['name'])
    lp = q("SELECT id FROM peaks WHERE is_leader=1", one=True)
    if lp and char['peak_id'] == lp['id']:
        original = q("SELECT name FROM peaks WHERE elder_id=? AND is_leader=0", (char['id'],), one=True)
        if original:
            return {**peak_specialty(original['name']), **specialty}
    return specialty

def _is_own_peak_technique(char, technique_key):
    own_peak_name = _technique_peak_name(char)
    pt = peak_technique(own_peak_name) if own_peak_name else None
    return bool(pt and pt['key'] == technique_key)

def _technique_affinity_score(char, technique_key):
    if _is_own_peak_technique(char, technique_key):
        return TECHNIQUE_OWN_PEAK_AFFINITY
    tech = PEAK_TECHNIQUES_BY_KEY.get(technique_key, {})
    score = TECHNIQUE_LEARNED_BASE_AFFINITY
    element = tech.get('element')
    mutation = ELEMENT_MUTATIONS.get(char['element_mutation']) if char.get('element_mutation') else None
    if element and mutation:
        score += TECHNIQUE_ELEMENT_MATCH_BONUS if mutation['element'] == element else -TECHNIQUE_ELEMENT_MATCH_BONUS
    return max(0, min(100, score))

def available_techniques(char):
    """通用三式人人可选 + 已持有的功法(自己峰的+机缘习得的),按篇章/熟练度/契合度实时算效果。"""
    techs = dict(CULTIVATE_METHODS)
    if not char:
        return techs
    rows = q("SELECT technique_key, mastery, insight FROM character_techniques WHERE char_id=?", (char['id'],))
    chapter_pct = technique_chapter_pct(char['realm_idx'])
    for row in rows:
        base = PEAK_TECHNIQUES_BY_KEY.get(row['technique_key'])
        if not base:
            continue
        mastery_pct = technique_mastery_pct(row['mastery'])
        affinity_score = _technique_affinity_score(char, row['technique_key'])
        affinity_label, affinity_pct = technique_affinity_band(affinity_score)
        mult = min(TECHNIQUE_LAYER_MULT_CAP, (1 + chapter_pct / 100) * (mastery_pct / 100) * (1 + affinity_pct / 100))
        tech = dict(base)
        tech['exp_mult'] = base['exp_mult'] * mult
        tech['mastery'] = row['mastery']
        tech['mastery_pct'] = mastery_pct
        tech['affinity_label'] = affinity_label
        tech['affinity_score'] = affinity_score
        tech['chapter_pct'] = chapter_pct
        tech['insight'] = row['insight']
        techs[row['technique_key']] = tech
    return techs

def in_retreat(char):
    return bool(char.get('retreat_until_ts')) and char['retreat_until_ts'] > now_ts()

def in_labor(char):
    return bool(char.get('labor_until_ts')) and char['labor_until_ts'] > now_ts()

def in_severe_injury(char):
    """游历遇险求援无人响应、过期后的重伤状态——和 in_retreat 一样挡打坐/委托/入秘境。"""
    return bool(char.get('severe_injury_until_ts')) and char['severe_injury_until_ts'] > now_ts()

# ── 洞府:灵气/清净/稳固三维只给已有系统(闭关/心魔/突破)加成,不落库,实时按品阶+阵法+方位算 ──

def _peak_name(char):
    if not char.get('peak_id'):
        return None
    row = q("SELECT name FROM peaks WHERE id=?", (char['peak_id'],), one=True)
    return row['name'] if row else None

def _technique_peak_name(char):
    """招式/功法练的是哪个峰的看这个,不等于住在哪个峰:掌门若仍兼任原峰长老(见 _install_leader),
    寄住掌门峰只影响拜师候选/洞府/峰属性加成这些"住在哪"的东西,练出来的招式和契合度仍跟着
    原峰功法走,不会因为peak_id挂到掌门峰就摔回0级的凌霄峰功法。"""
    if char.get('peak_id'):
        lp = q("SELECT id FROM peaks WHERE is_leader=1", one=True)
        if lp and char['peak_id'] == lp['id']:
            original = q("SELECT name FROM peaks WHERE elder_id=? AND is_leader=0", (char['id'],), one=True)
            if original:
                return original['name']
    return _peak_name(char)

def cave_qi(char):
    total = cave_tier_info(char['cave_tier'])['cave_qi']
    array = cave_array_info(char['cave_array_level'])
    if array:
        total += array['cave_qi']
    if char.get('cave_location') and char['cave_location'] != CAVE_LOCATION_COMMON:
        total += cave_location_bonus(char['cave_location']).get('cave_qi', 0)
    return max(0, total)

def cave_purity(char):
    total = cave_tier_info(char['cave_tier'])['cave_purity']
    if char.get('cave_location') and char['cave_location'] != CAVE_LOCATION_COMMON:
        total += cave_location_bonus(char['cave_location']).get('cave_purity', 0)
    return max(0, total)

def cave_stability(char):
    return cave_tier_info(char['cave_tier'])['cave_stability']

def cave_traits_list(char):
    try:
        return json.loads(char.get('cave_traits') or '[]')
    except (ValueError, TypeError):
        return []

def sync_cave_array(char):
    """聚灵阵日耗懒惰结算:灵石不够就直接停转降到0级,不会倒欠,跟体力回复一个模式。"""
    if not char['cave_array_level']:
        return char
    ts = char['cave_array_ts'] or char['created_ts']
    days = (now_ts() - ts) // 86400
    if days <= 0:
        return char
    array = cave_array_info(char['cave_array_level'])
    cost = array['daily_upkeep'] * days
    if cost <= 0:
        run("UPDATE characters SET cave_array_ts=? WHERE id=?", (now_ts(), char['id']))
    else:
        cur = run("UPDATE characters SET lingshi=lingshi-?, cave_array_ts=? WHERE id=? AND lingshi>=?",
                   (cost, now_ts(), char['id'], cost))
        if cur.rowcount > 0:
            char['lingshi'] -= cost
        else:
            run("UPDATE characters SET cave_array_level=0, cave_array_ts=? WHERE id=?", (now_ts(), char['id']))
            char['cave_array_level'] = 0
    char['cave_array_ts'] = now_ts()
    return char

def _material_qty(char_id, material_key):
    row = q("SELECT qty FROM character_materials WHERE char_id=? AND material_key=?",
            (char_id, material_key), one=True)
    return row['qty'] if row else 0

def _materials_owned(char_id):
    return {r['material_key']: r['qty'] for r in
            q("SELECT material_key, qty FROM character_materials WHERE char_id=?", (char_id,))}

def _has_materials(char_id, materials):
    return all(_material_qty(char_id, k) >= v for k, v in materials.items())

def _consume_materials(char_id, materials):
    """原子扣减多种材料;逐条按'当前qty>=待扣数'才真正扣减,避免并发重复提交把库存扣成负数
    (同 _spend 对 lingshi/contribution 的处理)。任意一种材料余量不足,已扣的会补回,整体不扣,返回是否成功。"""
    consumed = []
    for k, v in materials.items():
        cur = run("UPDATE character_materials SET qty=qty-? WHERE char_id=? AND material_key=? AND qty>=?",
                  (v, char_id, k, v))
        if cur.rowcount == 0:
            for ck, cv in consumed:
                run("UPDATE character_materials SET qty=qty+? WHERE char_id=? AND material_key=?", (cv, char_id, ck))
            return False
        consumed.append((k, v))
    return True

def _grant_material(char_id, material_key, qty=1):
    run("INSERT INTO character_materials (char_id,material_key,qty) VALUES (?,?,?) "
        "ON CONFLICT(char_id,material_key) DO UPDATE SET qty=qty+?", (char_id, material_key, qty, qty))

def _spend(char_id, column, amount):
    """原子扣减 lingshi/contribution 等余额字段,数据库层面带住"不够就不扣"这条线——
    单纯在Python里先查`char['lingshi']`够不够再UPDATE,两个并发请求会一起通过检查、一起扣款,
    扣穿成负数。column 只能传字面量(硬编码调用,不接受外部输入)。返回是否扣款成功。"""
    cur = run(f"UPDATE characters SET {column}={column}-? WHERE id=? AND {column}>=?", (amount, char_id, amount))
    return cur.rowcount > 0

def apply_reward(char_id, reward):
    specialty_row = q("""SELECT peaks.name FROM characters LEFT JOIN peaks ON peaks.id = characters.peak_id
                          WHERE characters.id=?""", (char_id,), one=True)
    specialty = peak_specialty(specialty_row['name']) if specialty_row and specialty_row['name'] else {}
    for key in _REWARD_FIELDS:
        val = reward.get(key)
        if not val:
            continue
        if key == 'reputation' and val > 0 and specialty.get('reputation_bonus_pct'):
            val = round(val * (1 + specialty['reputation_bonus_pct'] / 100))
        if key == 'contribution':
            run("UPDATE characters SET contribution=contribution+?, total_contribution=total_contribution+? "
                "WHERE id=?", (val, val, char_id))
        elif key == 'lifespan_years':
            run("UPDATE characters SET bonus_lifespan_years=bonus_lifespan_years+? WHERE id=?", (val, char_id))
        elif key == 'stamina':
            # 一次性奖励(突破/丹药/成就等)允许临时冲到 STAMINA_OVERFLOW_CAP,自然回复不会补到这个高度
            run("UPDATE characters SET stamina=MAX(0,MIN(?,stamina+?)) WHERE id=?",
                (STAMINA_OVERFLOW_CAP, val, char_id))
        elif key == 'mind_state':
            run("UPDATE characters SET mind_state=MAX(0,MIN(100,mind_state+?)) WHERE id=?", (val, char_id))
        elif key in ('physique', 'reputation', 'xiaxia_fame'):
            run(f"UPDATE characters SET {key}=MAX(0,{key}+?) WHERE id=?", (val, char_id))
        elif key == 'exp':
            # 修为的封顶不能只在打坐那一处挡——委托/秘境战利品/成就/兑换码等所有走这条通用发奖
            # 通道的来源,都得同时守住"没突破就攒不到下一级门槛以上"这条线,否则打坐那边的封顶等于白做。
            if val > 0:
                row = q("SELECT realm_idx, exp FROM characters WHERE id=?", (char_id,), one=True)
                if row and row['realm_idx'] < MAX_REALM_INDEX:
                    val = max(0, min(val, REALMS[row['realm_idx'] + 1]['exp'] - row['exp']))
            run("UPDATE characters SET exp=exp+? WHERE id=?", (val, char_id))
        else:
            run(f"UPDATE characters SET {key}=MAX(0,{key}+?) WHERE id=?", (val, char_id))

# ── 体力:懒惰结算,每次读取前按经过时间补齐 ────────────────────────────────────────

def sync_stamina(char):
    ts = char['stamina_ts'] or char['created_ts']
    gained = (now_ts() - ts) * STAMINA_REGEN_PER_HOUR // 3600
    if gained > 0:
        # 体力可能因一次性奖励溢出到 STAMINA_CAP 以上(见 apply_reward);被动回复只在未满员时补,
        # 不会把已经溢出的部分拉低回 STAMINA_CAP。
        if char['stamina'] < STAMINA_CAP:
            char['stamina'] = min(STAMINA_CAP, char['stamina'] + gained)
        char['stamina_ts'] = now_ts()
        run("UPDATE characters SET stamina=?, stamina_ts=? WHERE id=?",
            (char['stamina'], char['stamina_ts'], char['id']))
    elif not char['stamina_ts']:
        char['stamina_ts'] = now_ts()
        run("UPDATE characters SET stamina_ts=? WHERE id=?", (char['stamina_ts'], char['id']))
    return char

# ── 每日基础任务:每天随机抽3项,完成2/3项分别发放奖励 ───────────────────────────────

def ensure_daily_state(char_id):
    day = today_str()
    row = q("SELECT * FROM daily_state WHERE char_id=? AND day=?", (char_id, day), one=True)
    if row:
        return dict(row)
    keys = random.sample(list(DAILY_TASKS_BY_KEY.keys()), DAILY_TASKS_SHOWN)
    run("INSERT INTO daily_state (char_id,day,task_keys,done_keys,bonus_claimed,full_claimed) "
        "VALUES (?,?,?,?,0,0)", (char_id, day, json.dumps(keys), '[]'))
    return {'char_id': char_id, 'day': day, 'task_keys': json.dumps(keys), 'done_keys': '[]',
            'bonus_claimed': 0, 'full_claimed': 0}

def mark_daily_task(char_id, action_tag):
    state = ensure_daily_state(char_id)
    task_keys = json.loads(state['task_keys'])
    done_keys = json.loads(state['done_keys'])
    matched = False
    for key in task_keys:
        if key in done_keys:
            continue
        task = DAILY_TASKS_BY_KEY.get(key)
        if task and task['action'] == action_tag:
            done_keys.append(key)
            apply_reward(char_id, task['reward'])
            matched = True
            break  # 一次动作只推进一项日常,防止一个动作刷完多个同类任务
    if not matched:
        return
    run("UPDATE daily_state SET done_keys=? WHERE char_id=? AND day=?",
        (json.dumps(done_keys), char_id, state['day']))
    if len(done_keys) >= DAILY_TASKS_REQUIRED and not state['bonus_claimed']:
        apply_reward(char_id, DAILY_BONUS_REWARD)
        run("UPDATE daily_state SET bonus_claimed=1 WHERE char_id=? AND day=?", (char_id, state['day']))
        send_system_mail(char_id, '今日修行已完成', '完成了2项宗门日常,获得额外奖励。', from_label='宗门')
    if len(done_keys) >= DAILY_TASKS_SHOWN and not state['full_claimed']:
        apply_reward(char_id, DAILY_FULL_BONUS_REWARD)
        run("UPDATE daily_state SET full_claimed=1 WHERE char_id=? AND day=?", (char_id, state['day']))
        send_system_mail(char_id, '今日日常圆满', '三项日常全部完成,锦上添花。', from_label='宗门')

# ── 成就引擎:声明式条件,当前支持境界达成 / 门内档位达成 ──────────────────────────

def _achievement_condition_met(char, condition):
    ctype = condition.get('type')
    value = condition.get('value')
    if ctype == 'realm_reached':
        return char['realm_idx'] >= value
    if ctype == 'rank_reached':
        return char['rank_tier'] >= value
    if ctype == 'has_talent':
        return bool(char['talent_key'])
    if ctype == 'talent_major':
        return bool(char['talent_key']) and char['realm_idx'] >= TALENT_AWAKEN_REALM
    if ctype == 'has_immortal_bone':
        return bool(char['immortal_bone_key'])
    if ctype == 'ascended':
        return bool(char['ascended'])
    return False

def check_achievements(char_id):
    char = q("SELECT * FROM characters WHERE id=?", (char_id,), one=True)
    if not char:
        return
    got = {r['achievement_key'] for r in q(
        "SELECT achievement_key FROM char_achievements WHERE char_id=?", (char_id,))}
    for d in q("SELECT * FROM achievement_defs"):
        if d['key'] in got:
            continue
        if not _achievement_condition_met(char, json.loads(d['condition_json'])):
            continue
        try:
            run("INSERT INTO char_achievements (char_id,achievement_key,achieved_ts) VALUES (?,?,?)",
                (char_id, d['key'], now_ts()))
        except sqlite3.IntegrityError:
            continue
        reward = json.loads(d['reward_json'])
        send_system_mail(char_id, f"达成成就:{d['name']}", d['description'], attachment=reward)

# ── 宗门大事记:按宗门纪年(founded_ts起,1小时=1年)记录重大事件,供 /chronicle 只读展示 ──

def log_chronicle(text, major=False):
    cfg = q("SELECT founded_ts FROM sect_config WHERE id=1", one=True)
    year = game_year_of(now_ts(), cfg['founded_ts']) if cfg else 0
    run("INSERT INTO chronicle (year,text,is_major,created_ts) VALUES (?,?,?,?)",
        (year, text, 1 if major else 0, now_ts()))

# ── 寿元:角色年龄=创建以来经过的宗门纪年,耗尽后按境界判定"渡劫飞升"或"寿终正寝" ──────

def retire_character(char_id, outcome, label=None):
    char = q("SELECT * FROM characters WHERE id=?", (char_id,), one=True)
    if not char or char['ascended'] or char['deceased']:
        return
    label_was_custom = bool(label)
    if outcome == 'ascended':
        run("UPDATE characters SET ascended=1, ascend_ts=? WHERE id=?", (now_ts(), char_id))
        label = label or '寿元耗尽,渡劫飞升'
    else:
        label = label or '寿元耗尽,寿终正寝'
        run("UPDATE characters SET deceased=1, death_label=?, death_ts=? WHERE id=?", (label, now_ts(), char_id))
        # 师父身故是"一生只认一位师父"的唯一解绑条件——飞升则相反,师徒名分终身保留,不在这里处理。
        # 通知受影响的相关人等:徒弟们(可另寻良师)、自己的师父(若有)、以及所有在世的羁绊对象。
        my_disciples = q("SELECT disciple_id FROM discipleships WHERE master_id=? AND status IN ('active','pending')",
                          (char_id,))
        run("UPDATE discipleships SET status='ended' WHERE master_id=? AND status IN ('active','pending')", (char_id,))
        for d in my_disciples:
            send_system_mail(d['disciple_id'], '恩师仙逝',
                              f"你的师父{char['name']}寿元耗尽,溘然长逝。此后你已再无师承,"
                              "可前往「拜师」页面另寻良师,亦可去墓园祭拜。",
                              from_label='宗门·执事堂')
        my_master_row = q("SELECT master_id FROM discipleships WHERE disciple_id=? AND status='active'",
                           (char_id,), one=True)
        if my_master_row:
            send_system_mail(my_master_row['master_id'], '徒弟仙逝',
                              f"你的徒弟{char['name']}寿元耗尽,溘然长逝。", from_label='宗门·执事堂')
        # 羁绊(道侣/义结金兰)不在此自动解除,保留"active"作为纪念,在世一方要分开仍需自己去和离;
        # 但仍要私信告知,免得对方毫无察觉——想缅怀可去墓园探访。
        for bond in q("SELECT * FROM bonds WHERE status='active' AND (char_a_id=? OR char_b_id=?)",
                      (char_id, char_id)):
            partner_id = bond['char_b_id'] if bond['char_a_id'] == char_id else bond['char_a_id']
            bt_label = '道侣' if bond['bond_type'] == 'companion' else BOND_TYPES[bond['bond_type']]['label']
            send_system_mail(partner_id, f"{bt_label}仙逝",
                              f"你的{bt_label}{char['name']}寿元耗尽,溘然长逝。这段情谊仍系着,"
                              "若要另觅新缘,需自行前往解除;若只是思念,可去墓园祭拜。",
                              from_label='宗门·执事堂')
    run("UPDATE peaks SET elder_id=NULL WHERE elder_id=?", (char_id,))
    _close_leader_reign(char_id, outcome)  # 在任掌门这边退场(飞升/身故)才会真的改到东西,否则空操作
    send_system_mail(char_id, '大限已至', f"你{label}。", from_label='天道')
    title_suffix = f",道号「{char['dao_hao']}」" if char['dao_hao'] else ''
    # 自定义label(NPC让贤等特殊场景)、寿终正寝(不分境界,死讯本身就该让宗内人知道)、
    # 或金丹以上的高阶弟子飞升才算全宗大事;普通外门弟子飞升(1小时=1年,走得很快)太日常,
    # 不值得每次都刷屏——但"死了"这件事不受这条限制。
    is_notable = (bool(label_was_custom) or outcome == 'deceased'
                  or MAJOR_REALMS.index(realm_by_index(char['realm_idx'])['major']) >= MAJOR_BROADCAST_MIN_IDX)
    log_chronicle(f"{char['name']}({title_for(char['join_seq'], char['gender'])}){label}{title_suffix}",
                  major=is_notable)

def _character_age(char):
    """有基准(见 _ensure_story_columns 的迁移)就从基准往后按新速率算,没有基准(刚创建的新角色,
    整段人生都在提速之后)就直接从 created_ts 按新速率算——两条路径在基准刚冻结的那一刻是连续的,
    不会有人一夜暴增好几岁。"""
    if char['age_baseline_ts']:
        return char['age_baseline_years'] + (now_ts() - char['age_baseline_ts']) // AGE_SECONDS_PER_YEAR
    return STARTING_AGE_YEARS + (now_ts() - char['created_ts']) // AGE_SECONDS_PER_YEAR

def lifespan_tick():
    for char in q("SELECT * FROM characters WHERE ascended=0 AND deceased=0 AND is_npc=0"):
        age = _character_age(char)
        cap = lifespan_cap(char['realm_idx'], char['bonus_lifespan_years'])
        if age >= cap:
            outcome = 'ascended' if realm_major_idx(char['realm_idx']) >= ASCEND_ON_EXPIRY_MAJOR_IDX else 'deceased'
            retire_character(char['id'], outcome)
            continue
        remaining = cap - age
        if remaining <= LIFESPAN_FINAL_WARNING_YEARS and char['lifespan_final_warned_realm_idx'] != char['realm_idx']:
            run("UPDATE characters SET lifespan_final_warned_realm_idx=? WHERE id=?", (char['realm_idx'], char['id']))
            send_system_mail(char['id'], '大限将至',
                              f"你的寿元已不足{LIFESPAN_FINAL_WARNING_YEARS}年,近乎油尽灯枯——"
                              "再不设法(突破境界或炼制续命秘药),寿终正寝就在眼前。",
                              from_label='天道')
            log_chronicle(f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
                          f"寿元将尽,已不足{LIFESPAN_FINAL_WARNING_YEARS}年,命不久矣", major=True)
        if remaining * 100 <= cap * LIFESPAN_WARNING_PCT and char['lifespan_warned_realm_idx'] != char['realm_idx']:
            run("UPDATE characters SET lifespan_warned_realm_idx=? WHERE id=?", (char['realm_idx'], char['id']))
            send_system_mail(char['id'], '天机示警',
                              f"你的寿元只剩下约{remaining}年——当前境界寿元上限{cap}年,已耗去大半。"
                              "寻思着突破境界(寿元上限会跟着提高)或炼制续命秘药,莫要蹉跎到寿终正寝才追悔。",
                              from_label='天道')
        # 大乘圆满起天劫倒计时:到期前 DACHENG_ASCEND_WARNING_SECONDS 提醒一次,到期仍未飞升则身陨——
        # 跟寿元判定各自独立,不互相打断(上面 age>=cap 那支已经 continue 过了,走到这里说明寿元还没到)。
        if char['realm_idx'] == MAX_REALM_INDEX and char['dacheng_deadline_ts']:
            dacheng_remaining = char['dacheng_deadline_ts'] - now_ts()
            if dacheng_remaining <= 0:
                retire_character(char['id'], 'deceased', label=DACHENG_DEADLINE_DEATH_LABEL)
                continue
            if dacheng_remaining <= DACHENG_ASCEND_WARNING_SECONDS and not char['dacheng_warned']:
                run("UPDATE characters SET dacheng_warned=1 WHERE id=?", (char['id'],))
                send_system_mail(char['id'], '天劫将至', DACHENG_WARNING_FLAVOR, from_label='天道')

def retreat_labor_notify_tick():
    """闭关/打工到点后不会自动结算,得玩家自己回来点"出关"/"收工"——容易忘,时辰一到就提醒一次。"""
    ts = now_ts()
    for char in q("""SELECT id FROM characters WHERE ascended=0 AND deceased=0 AND is_npc=0
                      AND retreat_until_ts>0 AND retreat_until_ts<=? AND retreat_notify_sent=0""", (ts,)):
        send_system_mail(char['id'], '闭关时辰已到',
                          '闭关时辰已到,速回静室点击"出关"结算这次的收获,莫要一直挂在这忘了。',
                          from_label='宗门·执事堂')
        run("UPDATE characters SET retreat_notify_sent=1 WHERE id=?", (char['id'],))
    for char in q("""SELECT id FROM characters WHERE ascended=0 AND deceased=0 AND is_npc=0
                      AND labor_until_ts>0 AND labor_until_ts<=? AND labor_notify_sent=0""", (ts,)):
        send_system_mail(char['id'], '打工时辰已到',
                          '这份差事已经做完了,速回静室点击"收工"结算灵石,莫要忘了。',
                          from_label='宗门·执事堂')
        run("UPDATE characters SET labor_notify_sent=1 WHERE id=?", (char['id'],))

def sect_gossip_fire():
    """无视概率,强行编一段闲话写进大事记；返回是否成功(角色不足2人时不写)。供后台"手动触发"按钮
    和 sect_gossip_tick 共用。"""
    chars = q("SELECT id, name, join_seq, gender FROM characters WHERE ascended=0 AND deceased=0 AND is_npc=0")
    if len(chars) < 2:
        return False
    if len(chars) >= 3 and random.random() < SECT_GOSSIP_TRIO_CHANCE:
        a, b, c = random.sample(chars, 3)
        labels = [f"{p['name']}({title_for(p['join_seq'], p['gender'])})" for p in (a, b, c)]
        log_chronicle(random_gossip_text_trio(*labels), major=True)
    else:
        a, b = random.sample(chars, 2)
        a_label = f"{a['name']}({title_for(a['join_seq'], a['gender'])})"
        b_label = f"{b['name']}({title_for(b['join_seq'], b['gender'])})"
        log_chronicle(random_gossip_text(a_label, b_label), major=True)
    return True

def sect_gossip_tick():
    """后台随机挑两名在世弟子编一段日常闲话,纯叙事、不发奖励,写进大事记给宗门添点烟火气——
    不是每次tick都触发,概率见 SECT_GOSSIP_CHANCE,节奏由 run.py 的调用间隔控制。"""
    if random.random() < SECT_GOSSIP_CHANCE:
        sect_gossip_fire()

# ── 掌门继任:掌门峰空缺不再自动递补,须由在位长老主动申请;若已有人在位,后来者申请即
# 视为挑战,双方按战力算分+运气PK一场,赢家坐镇掌门峰,原掌门降回原峰长老 ────────────────

def leader_peak():
    return q("SELECT * FROM peaks WHERE is_leader=1", one=True)

def current_leader():
    row = q("""SELECT characters.* FROM peaks JOIN characters ON characters.id = peaks.elder_id
               WHERE peaks.is_leader=1""", one=True)
    return dict(row) if row else None

def leader_application_open():
    """掌门位是否已到可申请的时点——开服头几天{cfg.npc_leader_name}尚未离宗前不受理申请。"""
    cfg = q("SELECT * FROM sect_config WHERE id=1", one=True)
    return bool(cfg['succession_done']) or now_ts() >= cfg['succession_target_ts']

def _close_leader_reign(char_id, end_reason, defeated_by_char_id=None):
    """卸任掌门(被挑落/飞升/身故都走这)——只结束那条还开着的在位纪录,不是掌门则天然是空操作。"""
    run("UPDATE leader_history SET ended_ts=?, end_reason=?, defeated_by_char_id=? "
        "WHERE char_id=? AND ended_ts IS NULL", (now_ts(), end_reason, defeated_by_char_id, char_id))

def _install_leader(new_leader, lp, announce_text):
    """继任/夺位后落位:新掌门移驻掌门峰兼任原峰长老(原峰长老之位仍挂其名,不清空)。"""
    run("UPDATE characters SET rank_tier=6, peak_id=? WHERE id=?", (lp['id'], new_leader['id']))
    run("UPDATE peaks SET elder_id=? WHERE id=?", (new_leader['id'], lp['id']))
    run("INSERT INTO leader_history (char_id, started_ts) VALUES (?, ?)", (new_leader['id'], now_ts()))
    check_achievements(new_leader['id'])
    for c in q("SELECT id FROM characters"):
        send_system_mail(c['id'], '掌门更替', announce_text, from_label='宗门公告')
    run("INSERT INTO admin_logs (admin_id,target_type,target_id,action,detail,created_ts) VALUES (?,?,?,?,?,?)",
        (None, 'character', new_leader['id'], 'succession', f"{new_leader['name']} 继任掌门", now_ts()))
    log_chronicle(f"{new_leader['name']}({title_for(new_leader['join_seq'], new_leader['gender'])})继任{SECT_NAME}掌门,坐镇{lp['name']}",
                  major=True)

def ascend_leader():
    """后台手动操作:令现任掌门飞升离宗,掌门位空出,须有长老主动申请方能补上。"""
    lp = leader_peak()
    if not lp or not lp['elder_id']:
        return False
    outgoing = q("SELECT * FROM characters WHERE id=?", (lp['elder_id'],), one=True)
    run("UPDATE characters SET ascended=1, ascend_ts=? WHERE id=?", (now_ts(), outgoing['id']))
    # 掌门可能仍兼任原峰长老(见 _install_leader),两处任职一并清空,
    # 否则原峰会留一个指向已飞升角色的僵尸长老。
    run("UPDATE peaks SET elder_id=NULL WHERE elder_id=?", (outgoing['id'],))
    _close_leader_reign(outgoing['id'], 'ascended')
    for c in q("SELECT id FROM characters"):
        send_system_mail(c['id'], '掌门飞升',
                          f"掌门{outgoing['name']}道行圆满,今日飞升离宗,{lp['name']}掌门之位暂缺,静候长老主动申请继任。",
                          from_label='宗门公告')
    run("INSERT INTO admin_logs (admin_id,target_type,target_id,action,detail,created_ts) VALUES (?,?,?,?,?,?)",
        (S.get('real_admin_uid', S.get('uid')), 'character', outgoing['id'], 'ascend_leader',
         f"{outgoing['name']} 飞升离宗", now_ts()))
    log_chronicle(f"掌门{outgoing['name']}道行圆满,飞升离宗", major=True)
    return True

# ── 首页 ───────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'uid' in S:
        if S.get('role') == 'admin':
            return redirect(url_for('admin_home'))
        return redirect(url_for('home'))
    return redirect(url_for('login'))

# ── 注册(需管理员审核,填有效邀请码可直接免审) ───────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        qq       = request.form.get('qq', '').strip()
        invite   = request.form.get('invite_code', '').strip()

        err = None
        if not (2 <= len(username) <= 20):
            err = '用户名长度需在 2-20 位之间'
        elif len(password) < 6:
            err = '密码至少 6 位'
        elif not qq.isdigit() or not (5 <= len(qq) <= 11):
            err = 'QQ 号需为 5-11 位数字'
        elif q("SELECT id FROM users WHERE username=?", (username,), one=True):
            err = '用户名已被占用'

        if err:
            flash(err, 'error')
            return render_template('register.html', form={'username': username, 'qq': qq, 'invite_code': invite})

        status = 'pending'
        if invite:
            invite_row = q("SELECT * FROM invite_codes WHERE code=?", (invite,), one=True)
            valid = (invite_row and invite_row['used_count'] < invite_row['max_uses']
                      and (not invite_row['expires_ts'] or invite_row['expires_ts'] > now_ts()))
            if valid:
                status = 'approved'
                run("UPDATE invite_codes SET used_count=used_count+1 WHERE id=?", (invite_row['id'],))
            else:
                flash('邀请码无效或已失效,已按普通注册提交审核', 'error')

        run("INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(password, method='pbkdf2:sha256'), qq,
             'player', status, now_ts()))

        if status == 'approved':
            return redirect(url_for('login'))
        return redirect(url_for('register_pending'))

    return render_template('register.html', form={})

@app.route('/register/pending')
def register_pending():
    return render_template('register_pending.html')

# ── 登录 / 登出 ─────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if not user or not check_password_hash(user['password_hash'], password):
            err = '账号或密码错误'
        elif user['status'] == 'pending':
            err = '账号审核中,请等待管理员审核'
        elif user['status'] == 'rejected':
            err = '账号审核未通过'
        elif user['status'] == 'deleted':
            err = '该账号已被管理员删除'
        else:
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = user['role']
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            if user['role'] == 'admin':
                return redirect(url_for('admin_home'))
            char = q("SELECT id FROM characters WHERE user_id=?", (user['id'],), one=True)
            return redirect(url_for('home') if char else url_for('create_character'))
    return render_template('login.html', err=err)

@app.route('/logout')
def logout():
    S.clear()
    return redirect(url_for('login'))

# ── 管理员专用登录 ───────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    err = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = q("SELECT * FROM users WHERE username=?", (username,), one=True)
        if user and user['role'] == 'admin' and check_password_hash(user['password_hash'], password):
            S.permanent = True
            S['uid'] = user['id']; S['uname'] = user['username']; S['role'] = 'admin'
            run("UPDATE users SET last_login=? WHERE id=?", (now_ts(), user['id']))
            return redirect(url_for('admin_home'))
        err = '账号或密码错误(仅管理员可用此入口)'
    return render_template('admin_login.html', err=err)

# ── 山门辨灵石:入宗前的小仪式,手动点、不惰性自动结算,第5次必过 ───────────────────────

@app.route('/spirit_test', methods=['GET', 'POST'])
@login_required
def spirit_test():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    if me_character():
        return redirect(url_for('home'))
    user = q("SELECT * FROM users WHERE id=?", (S['uid'],), one=True)
    if user['spirit_test_passed']:
        return redirect(url_for('create_character'))

    attempt_number = user['spirit_test_attempts'] + 1
    chance = spirit_test_chance_pct(attempt_number)
    next_ts = user['spirit_test_last_ts'] + SPIRIT_TEST_COOLDOWN_SECONDS if user['spirit_test_attempts'] else 0
    can_attempt = now_ts() >= next_ts

    if request.method == 'POST':
        if not can_attempt:
            flash('灵石尚在沉寂,时机未到', 'error')
            return redirect(url_for('spirit_test'))
        cur = run("""UPDATE users SET spirit_test_attempts=spirit_test_attempts+1, spirit_test_last_ts=?
                     WHERE id=? AND spirit_test_attempts=?""",
                  (now_ts(), S['uid'], user['spirit_test_attempts']))
        if cur.rowcount == 0:
            flash('灵石尚在沉寂,时机未到', 'error')
            return redirect(url_for('spirit_test'))
        if random.random() * 100 <= chance:
            run("UPDATE users SET spirit_test_passed=1 WHERE id=?", (S['uid'],))
            flash(SPIRIT_TEST_SUCCESS_TEXT, 'ok')
            return redirect(url_for('create_character'))
        flash(random.choice(SPIRIT_TEST_FAIL_FLAVORS), 'error')
        return redirect(url_for('spirit_test'))

    wait_seconds = max(0, next_ts - now_ts())
    return render_template('spirit_test.html', attempt_number=attempt_number, chance=chance,
                            can_attempt=can_attempt, wait_seconds=wait_seconds)

# ── 角色创建(审核通过后首次进入) ─────────────────────────────────────────────────

@app.route('/create_character', methods=['GET', 'POST'])
@login_required
def create_character():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    if me_character():
        return redirect(url_for('home'))

    prior = q("SELECT * FROM characters WHERE user_id=? ORDER BY created_ts DESC", (S['uid'],))
    user = q("SELECT * FROM users WHERE id=?", (S['uid'],), one=True)
    # 飞升证道是终局,不给转世机会——哪怕这是第一次结束也直接拦下,只留仙籍继续玩;
    # 转世机会仅对"寿终正寝"这类非飞升的结束保留一次,由 reincarnated 标记把关。
    ever_ascended = any(p['ascended'] for p in prior)
    if prior and (ever_ascended or user['reincarnated']):
        return render_template('reincarnation_denied.html', prior=prior, title_for=title_for,
                                ever_ascended=ever_ascended)
    if not user['spirit_test_passed']:
        return redirect(url_for('spirit_test'))

    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip()
        bio    = request.form.get('bio', '').strip()

        err = None
        if not (1 <= len(name) <= 12):
            err = '道号长度需在 1-12 位之间'
        elif gender not in ('m', 'f'):
            err = '请选择师兄/师姐'

        if err:
            flash(err, 'error')
            return render_template('create_character.html', name=name, gender=gender, bio=bio, prior=prior)

        next_seq = (q("SELECT COALESCE(MAX(join_seq),0) s FROM characters WHERE is_npc=0", one=True)['s'] or 0) + 1
        new_spirit_root = roll_spirit_root()
        new_spirit_root_elements = roll_spirit_root_elements(new_spirit_root)
        cur = run("INSERT INTO characters (user_id,name,gender,bio,realm_idx,exp,rank_tier,join_seq,"
                   "contribution,total_contribution,spirit_root,spirit_root_elements,talent_key,element_mutation,created_ts) "
                   "VALUES (?,?,?,?,0,0,0,?,0,0,?,?,?,?,?)",
                   (S['uid'], name, gender, bio, next_seq, new_spirit_root,
                    ','.join(new_spirit_root_elements) if new_spirit_root_elements else None,
                    roll_bloodline(), roll_element_mutation(), now_ts()))
        if prior:
            run("UPDATE users SET reincarnated=1 WHERE id=?", (S['uid'],))
            log_chronicle(f"{name}({title_for(next_seq, gender)})转世入宗,承续前尘", major=True)
        else:
            log_chronicle(f"{name}({title_for(next_seq, gender)})拜入{SECT_NAME},列为外门弟子")
        run("""UPDATE users SET spirit_test_passed=0, spirit_test_attempts=0, spirit_test_last_ts=0
               WHERE id=?""", (S['uid'],))
        check_achievements(cur.lastrowid)
        send_system_mail(cur.lastrowid, '入门指引·打坐修炼',
                          '静室里选一种打坐方式,点击即可攒修为——静心吐纳最稳,引气入体更快但偶有走火,'
                          '深度入定收益最高但冷却更久。修为攒够下一境界的门槛后,静室会出现"前往突破"的提示,'
                          '届时再去尝试渡劫。其余的委托、探索、峰门之类,不急,等你摸熟这一步再说。',
                          from_label='宗门·执事堂')
        return redirect(url_for('home'))

    return render_template('create_character.html', name='', gender='', bio='', prior=prior)

# ── 首页"下一步行动":纯函数,只读home()里已经算好的数据,不额外查库,最多给3条按优先级排序 ──

def recommend_next_actions(char, next_realm, weapon_discipline, daily_tasks_today, dao_paths):
    actions = []
    if next_realm and char['exp'] >= next_realm['exp']:
        actions.append({'label': '修为已足', 'detail': f"可尝试突破{next_realm['name']}",
                         'href': url_for('breakthrough_home')})
    if weapon_discipline.get('next_threshold'):
        gap = weapon_discipline['next_threshold'] - weapon_discipline['mastery']
        if 0 < gap <= 5:
            next_title = WEAPON_MASTERY_TITLES[weapon_discipline['level'] + 1]
            actions.append({'label': f"{weapon_discipline['label']}将近",
                             'detail': f"距离「{next_title}」还差{gap}点熟练",
                             'href': url_for('mystic_home')})
    if (char['stamina'] >= STAMINA_CAP * 0.7 and not in_severe_injury(char) and not in_retreat(char)):
        actions.append({'label': '体力充足', 'detail': '适合去委托/游历/秘境走一趟',
                         'href': url_for('commissions_list')})
    undone = next((t for t in daily_tasks_today if not t['done']), None)
    if undone:
        actions.append({'label': '今日修行', 'detail': f"「{undone['label']}」尚未完成", 'href': url_for('home')})
    eligible_path = next((p for p in dao_paths if p['eligible'] and not p['chosen']), None)
    if eligible_path:
        actions.append({'label': '道途候选', 'detail': f"已达成{eligible_path['label']}的资格,可以选择立道",
                         'href': url_for('home')})
    return actions[:3]

# ── 玩家首页(静室) ───────────────────────────────────────────────────────────────

@app.route('/home')
@login_required
def home():
    if S.get('role') == 'admin':
        return redirect(url_for('admin_home'))
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = ensure_character_story(sync_stamina(char))
    mark_daily_task(char['id'], 'checkin')
    pending_result = S.pop('pending_result', None)
    last_cultivate = S.get('last_cultivate_ts', 0)
    cultivate_cooldown_remaining = max(0, CULTIVATE_COOLDOWN_SECONDS - (now_ts() - last_cultivate)) if last_cultivate else 0
    cultivate_diminish_done = get_daily_counter(char['id'], 'cultivate_diminish')
    my_rescue_call = q("SELECT * FROM travel_rescue_calls WHERE char_id=? ORDER BY id DESC LIMIT 1",
                        (char['id'],), one=True)
    if my_rescue_call and my_rescue_call['status'] == 'open':
        my_rescue_call = _travel_rescue_resolve_expiry(dict(my_rescue_call))
        char = dict(q("SELECT * FROM characters WHERE id=?", (char['id'],), one=True))
    open_rescue_calls = []
    for row in q("""SELECT trc.*, c.name char_name, c.join_seq, c.gender FROM travel_rescue_calls trc
                     JOIN characters c ON c.id = trc.char_id
                     WHERE trc.status='open' AND trc.char_id!=? AND trc.expires_ts>?
                     ORDER BY trc.created_ts DESC LIMIT 5""", (char['id'], now_ts())):
        claimed_active = row['claimed_by'] and row['claim_expires_ts'] > now_ts()
        if claimed_active and row['claimed_by'] != char['id']:
            continue  # 已被别人认领在处理,别再冒出来抢
        open_rescue_calls.append(dict(row, can_complete=bool(claimed_active and row['claimed_by'] == char['id'])))
    daily_state = ensure_daily_state(char['id'])
    done_keys = json.loads(daily_state['done_keys'])
    daily_tasks_today = [DAILY_TASKS_BY_KEY[k] | {'done': k in done_keys}
                          for k in json.loads(daily_state['task_keys'])]

    realm = realm_by_index(char['realm_idx'])
    next_realm = REALMS[char['realm_idx'] + 1] if char['realm_idx'] < MAX_REALM_INDEX else None
    if next_realm:
        span = next_realm['exp'] - realm['exp']
        progress = (char['exp'] - realm['exp']) / span if span else 0
        realm_progress_pct = max(0, min(100, round(progress * 100)))
    else:
        realm_progress_pct = 100

    rank = rank_by_tier(char['rank_tier'])
    next_rank = rank_by_tier(char['rank_tier'] + 1) if char['rank_tier'] < len(RANKS) - 1 else None

    peak = q("SELECT * FROM peaks WHERE id=?", (char['peak_id'],), one=True) if char['peak_id'] else None
    as_master = q("SELECT c.name, c.id FROM discipleships d JOIN characters c ON c.id = d.disciple_id "
                  "WHERE d.master_id=? AND d.status='active'", (char['id'],))
    as_disciple = q("SELECT c.name, c.id, c.zi FROM discipleships d JOIN characters c ON c.id = d.master_id "
                    "WHERE d.disciple_id=? AND d.status='active'", (char['id'],), one=True)

    leader = current_leader()
    cfg = q("SELECT * FROM sect_config WHERE id=1", one=True)

    talent_info = None
    if char['talent_key']:
        pct, stat, is_major = talent_stage_pct(char['talent_key'], char['realm_idx'])
        talent_info = {'label': TALENTS[char['talent_key']]['label'], 'source': TALENTS[char['talent_key']]['source'],
                        'pct': pct, 'stat': '修为' if stat == 'exp' else '贡献', 'is_major': is_major}
    bone_label = IMMORTAL_BONES[char['immortal_bone_key']]['label'] if char['immortal_bone_key'] else None
    bone_bonus = IMMORTAL_BONES[char['immortal_bone_key']]['bonus'] if char['immortal_bone_key'] else None
    mutation_label = element_mutation_label(char['element_mutation'])

    age_years = _character_age(char)
    lifespan_years = lifespan_cap(char['realm_idx'], char['bonus_lifespan_years'])
    lifespan_remaining = lifespan_years - age_years
    lifespan_warning = lifespan_remaining * 100 <= lifespan_years * LIFESPAN_WARNING_PCT
    sect_year = game_year_of(now_ts(), cfg['founded_ts'])
    mind_band = mind_state_band(char['mind_state'])
    my_bonds = get_bonds(char['id'])
    bonds_sent, bonds_received = get_pending_bonds(char['id'])
    specialty = get_peak_specialty(char)
    _resolve_pet_holding_expiry(char['id'])
    equipped_pet = q("SELECT * FROM character_pets WHERE id=?", (char['equipped_pet_id'],), one=True) \
        if char['equipped_pet_id'] else None
    pet_info = PET_TYPES[equipped_pet['pet_key']] if equipped_pet else None
    sense_unlocked = spirit_sense_unlocked(char['realm_idx'])
    stability = spirit_sea_stability(char['mind_state'], char['technique_deviation'])
    dao_rows = {r['path_key']: dict(r) for r in q(
        "SELECT path_key,progress,unlocked_ts FROM character_dao_paths WHERE char_id=?", (char['id'],))}
    chosen_path = chosen_dao_path(char['id'])
    dao_paths = [dict(info, key=key, progress=dao_rows.get(key, {}).get('progress', 0),
                      eligible=bool(dao_rows.get(key, {}).get('unlocked_ts')), chosen=key == chosen_path,
                      daily_cap=DAO_DAILY_CAPS.get(key),
                      daily_used=get_daily_counter(char['id'], f'dao_{key}') if key in DAO_DAILY_CAPS else None)
                 for key, info in DAO_PATHS.items()]
    weapon_discipline = _weapon_mastery_profile(char)
    next_actions = recommend_next_actions(char, next_realm, weapon_discipline, daily_tasks_today, dao_paths)

    return render_template('home.html', char=char, realm=realm, next_realm=next_realm,
                            sense_unlocked=sense_unlocked, spirit_sense_value=spirit_sense(char['realm_idx']),
                            spirit_sea_stability_value=stability,
                            my_bonds=my_bonds, bonds_sent=bonds_sent, bonds_received=bonds_received,
                            BOND_TYPES=BOND_TYPES, specialty=specialty, pet_info=pet_info, equipped_pet=equipped_pet,
                            pet_max_level=pet_max_level(equipped_pet['pet_key']) if equipped_pet else PET_MAX_LEVEL,
                            pet_quality_info=PET_QUALITIES[pet_quality(equipped_pet['pet_key'])] if equipped_pet else None,
                            pet_image_url=pet_image_url, pet_exp_per_level=PET_EXP_PER_LEVEL,
                            pet_train_cost=PET_TRAIN_STAMINA_COST, pet_train_limit=PET_TRAIN_DAILY_LIMIT,
                            pet_adopt_cost=PET_ADOPT_STAMINA_COST,
                            pet_adopt_left=max(0, PET_ADOPT_DAILY_LIMIT - get_daily_counter(char['id'], 'pet_adopt')),
                            realm_progress_pct=realm_progress_pct, rank=rank, next_rank=next_rank,
                            peak=peak, as_master=as_master, as_disciple=as_disciple,
                            leader=leader, cfg=cfg, spirit_root_label=spirit_root_label,
                            spirit_root_elements_label=spirit_root_elements_label,
                            talent_info=talent_info, bone_label=bone_label, bone_bonus=bone_bonus, mutation_label=mutation_label,
                            age_years=age_years, lifespan_years=lifespan_years, sect_year=sect_year,
                            lifespan_remaining=lifespan_remaining, lifespan_warning=lifespan_warning,
                            mind_band=mind_band, stamina_cap=STAMINA_CAP,
                            techniques=available_techniques(char),
                            retreat_active=bool(char['retreat_started_ts']),
                            retreat_ready=bool(char['retreat_started_ts']) and now_ts() >= char['retreat_until_ts'],
                            retreat_remaining=max(0, char['retreat_until_ts'] - now_ts()),
                            labor_active=bool(char['labor_started_ts']),
                            labor_ready=bool(char['labor_started_ts']) and now_ts() >= char['labor_until_ts'],
                            labor_remaining=max(0, char['labor_until_ts'] - now_ts()),
                            dacheng_remaining=max(0, char['dacheng_deadline_ts'] - now_ts()) if char['dacheng_deadline_ts'] else None,
                            daily_tasks_today=daily_tasks_today, daily_required=DAILY_TASKS_REQUIRED,
                            daily_shown=DAILY_TASKS_SHOWN,
                            cultivate_cooldown=CULTIVATE_COOLDOWN_SECONDS, dao_paths=dao_paths,
                            cultivate_diminish_done=cultivate_diminish_done,
                            cultivate_diminish_after=CULTIVATE_DIMINISH_AFTER,
                            chosen_dao_path=chosen_path, weapon_discipline=weapon_discipline,
                            next_actions=next_actions,
                            severe_injury=in_severe_injury(char),
                            severe_injury_remaining=max(0, (char['severe_injury_until_ts'] or 0) - now_ts()),
                            my_rescue_call=my_rescue_call, open_rescue_calls=open_rescue_calls,
                            title_for=title_for, now_ts=now_ts(), pending_result=pending_result,
                            cultivate_cooldown_remaining=cultivate_cooldown_remaining,
                            tiandi_boost_cost=TIANDI_STAMINA_BOOST_COST, tiandi_boost_amount=TIANDI_STAMINA_BOOST_AMOUNT,
                            tiandi_boost_left=max(0, TIANDI_STAMINA_BOOST_DAILY_CAP
                                                   - get_daily_counter(char['id'], 'tiandi_stamina_boost')),
                            tiandi_boost_cap=TIANDI_STAMINA_BOOST_DAILY_CAP)

# ── 天地精华:预留付费货币,充值入口暂未真正开放(点击只提示敬请期待),消耗口先实装 ──────

RECHARGE_EASTER_EGG_COUNTER_KEY = 'recharge_easter_egg'  # 5个档位共用同一把锁,中一次全灰,不是各档位独立

@app.route('/recharge')
@login_required
def recharge_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    easter_egg_used_today = get_daily_counter(char['id'], RECHARGE_EASTER_EGG_COUNTER_KEY) >= 1
    return render_template('recharge.html', char=char, tiers=TIANDI_JINGHUA_TIERS,
                            shop_weapons=TIANDI_SHOP_WEAPONS, shop_weapon_cost=TIANDI_SHOP_WEAPON_COST,
                            ELEMENTS=ELEMENTS, easter_egg_used_today=easter_egg_used_today)

@app.route('/recharge/buy', methods=['POST'])
@login_required
def recharge_buy():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    price_cny = request.form.get('price_cny', type=int)
    tier = next((t for t in TIANDI_JINGHUA_TIERS if t['price_cny'] == price_cny), None)
    if not tier:
        # 商城武器等非充值档位的按钮,维持纯展示反馈,不涉及每日次数
        flash(random.choice(TIANDI_FAKE_BUY_FLAVORS), 'ok')
        return redirect(url_for('recharge_home'))
    if get_daily_counter(char['id'], RECHARGE_EASTER_EGG_COUNTER_KEY) >= 1:
        flash('今日已经中过一次了,五个档位共享这份运气,明日再来', 'error')
        return redirect(url_for('recharge_home'))
    if random.random() < TIANDI_EASTER_EGG_CHANCE:
        bump_daily_counter(char['id'], RECHARGE_EASTER_EGG_COUNTER_KEY)
        apply_reward(char['id'], {'tiandi_jinghua': TIANDI_EASTER_EGG_AMOUNT})
        flash(random.choice(TIANDI_EASTER_EGG_FLAVORS), 'ok')
    else:
        flash(random.choice(TIANDI_FAKE_BUY_FLAVORS), 'ok')
    return redirect(url_for('recharge_home'))

@app.route('/tiandi/shop/buy/<item_key>', methods=['POST'])
@login_required
def tiandi_shop_buy(item_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    weapon = next((w for w in TIANDI_SHOP_WEAPONS if w['key'] == item_key), None)
    if not weapon:
        flash('商品不存在', 'error')
        return redirect(url_for('recharge_home'))
    if not _spend(char['id'], 'tiandi_jinghua', TIANDI_SHOP_WEAPON_COST):
        flash(f"天地精华不够,还差{TIANDI_SHOP_WEAPON_COST - char['tiandi_jinghua']}点", 'error')
        return redirect(url_for('recharge_home'))
    _inventory_grant(char['id'], 'gear', 1, item_key)
    if _equipment_locked(char):
        flash(f"购得「{weapon['label']}」,已放入行囊——秘境/游历途中不能换装,回来后自行装备", 'ok')
    elif not _weapon_usable(char, weapon):
        flash(f"购得「{weapon['label']}」,已放入行囊——但你的灵根属性不合,驾驭不了,需自行找机会换装", 'ok')
    elif _equip_item_silent(char, 'weapon', item_key):
        flash(f"购得「{weapon['label']}」,已直接为你换上!", 'ok')
    else:
        flash(f"购得「{weapon['label']}」,已放入行囊", 'ok')
    return redirect(url_for('recharge_home'))

@app.route('/tiandi/stamina_boost', methods=['POST'])
@login_required
def tiandi_stamina_boost():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    if char['stamina'] >= STAMINA_CAP:
        flash('体力已满,无需加速', 'error')
        return redirect(url_for('home'))
    if get_daily_counter(char['id'], 'tiandi_stamina_boost') >= TIANDI_STAMINA_BOOST_DAILY_CAP:
        flash(f"今日已用天地精华加速{TIANDI_STAMINA_BOOST_DAILY_CAP}次,明日再来", 'error')
        return redirect(url_for('home'))
    if not _spend(char['id'], 'tiandi_jinghua', TIANDI_STAMINA_BOOST_COST):
        flash(f"天地精华不足{TIANDI_STAMINA_BOOST_COST}", 'error')
        return redirect(url_for('home'))
    bump_daily_counter(char['id'], 'tiandi_stamina_boost')
    run("UPDATE characters SET stamina=MIN(?,stamina+?) WHERE id=?",
        (STAMINA_CAP, TIANDI_STAMINA_BOOST_AMOUNT, char['id']))
    flash(f"以天地精华×{TIANDI_STAMINA_BOOST_COST}加速运转,体力+{TIANDI_STAMINA_BOOST_AMOUNT}", 'ok')
    return redirect(url_for('home'))

@app.route('/dao/choose/<path_key>', methods=['POST'])
@login_required
def dao_path_choose(path_key):
    char = me_character()
    path = DAO_PATHS.get(path_key)
    if not char or not path:
        flash('道途不存在', 'error')
        return redirect(url_for('home'))
    if char.get('dao_path_key'):
        chosen = DAO_PATHS.get(char['dao_path_key'], {}).get('label', char['dao_path_key'])
        flash(f'你已立下{chosen}，一人只能正式选择一条道途', 'error')
        return redirect(url_for('home'))
    eligible = q("SELECT 1 FROM character_dao_paths WHERE char_id=? AND path_key=? AND unlocked_ts IS NOT NULL",
                 (char['id'], path_key), one=True)
    if not eligible:
        flash(f"尚未达成{path['requirement']}，无法选择{path['label']}", 'error')
        return redirect(url_for('home'))
    ts = now_ts()
    cur = run("UPDATE characters SET dao_path_key=?,dao_path_chosen_ts=? WHERE id=? AND dao_path_key IS NULL",
              (path_key, ts, char['id']))
    if cur.rowcount == 0:
        flash('道途已由另一项选择确定，请刷新查看', 'error')
        return redirect(url_for('home'))
    send_system_mail(char['id'], f"立道·{path['label']}",
                     f"你正式立下{path['label']}。从此此道伴随终身，永久效果：{path['bonus_desc']}。",
                     from_label='大道感应')
    log_chronicle(f"{char['name']}立下{path['label']}")
    flash(f"立道功成！你选择了{path['label']}，获得永久效果：{path['bonus_desc']}", 'ok')
    return redirect(url_for('home'))

@app.route('/character/rename', methods=['POST'])
@login_required
def character_rename():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    name = request.form.get('name', '').strip()
    if not (1 <= len(name) <= 12):
        flash('道号长度需在 1-12 位之间', 'error')
        return redirect(url_for('home'))
    old_name = char['name']
    run("UPDATE characters SET name=? WHERE id=?", (name, char['id']))
    if name != old_name:
        log_chronicle(f"{old_name}更名为{name}")
    flash(f"道号已更名为{name}", 'ok')
    return redirect(url_for('home'))

@app.route('/character/face_claim', methods=['POST'])
@login_required
def character_face_claim():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    face_claim = request.form.get('face_claim', '').strip()
    if not face_claim:
        run("UPDATE characters SET face_claim=NULL WHERE id=?", (char['id'],))
        flash('已清空皮相', 'ok')
        return redirect(url_for('home'))
    if not (1 <= len(face_claim) <= 20):
        flash('皮相名称长度需在 1-20 位之间', 'error')
        return redirect(url_for('home'))
    taken = q("SELECT name FROM characters WHERE LOWER(face_claim)=LOWER(?) AND id!=?",
              (face_claim, char['id']), one=True)
    if taken:
        flash(f"这个皮相已被{taken['name']}注册,换一个吧", 'error')
        return redirect(url_for('home'))
    run("UPDATE characters SET face_claim=? WHERE id=?", (face_claim, char['id']))
    flash(f"已注册皮相「{face_claim}」", 'ok')
    return redirect(url_for('home'))

@app.route('/cultivate/<method>', methods=['POST'])
@login_required
def cultivate(method):
    char = me_character()
    if not char:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='角色不存在'), 404
        return redirect(url_for('create_character'))
    if in_retreat(char):
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='你正在闭关中,心无旁骛'), 409
        flash('你正在闭关中,心无旁骛,出关后再来', 'error')
        return redirect(url_for('retreat_home'))
    if in_labor(char):
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='你正在外出打工,分身乏术'), 409
        flash('你正在外出打工,分身乏术,出工后再来', 'error')
        return redirect(url_for('labor_home'))
    techniques = available_techniques(char)
    if method not in techniques:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='未知或尚未习得的打坐方式'), 400
        flash('未知或尚未习得的打坐方式', 'error')
        return redirect(url_for('home'))
    cm = techniques[method]

    done_today = get_daily_counter(char['id'], 'cultivate_diminish')
    diminished = done_today >= CULTIVATE_DIMINISH_AFTER
    if done_today >= CULTIVATE_DIMINISH_AFTER + CULTIVATE_DIMINISH_HARD_CAP_EXTRA:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='今日打坐已严重超量,明日再来'), 429
        flash('今日打坐已严重超量,明日再来', 'error')
        return redirect(url_for('home'))
    cooldown = CULTIVATE_COOLDOWN_SECONDS * cm['cooldown_mult'] * (
        CULTIVATE_DIMINISH_COOLDOWN_MULT if diminished else 1)
    last = S.get('last_cultivate_ts', 0)
    if now_ts() - last < cooldown:
        if request.accept_mimetypes.best == 'application/json':
            remaining = cooldown - (now_ts() - last)
            return jsonify(ok=False, message='灵息尚未平复', cooldown_remaining=max(1, remaining)), 429
        flash('刚刚打坐过,稍后再来', 'error')
        return redirect(url_for('home'))
    S['last_cultivate_ts'] = now_ts()

    # ── 机缘判定:无血脉/传承者可能获得传承;无仙骨者可能觅得仙骨(每种全宗唯一,先到先得) ──
    notices = []
    if not char['talent_key'] and random.random() < INHERITANCE_ROLL_CHANCE:
        talent_key = random.choice(INHERITANCE_KEYS)
        run("UPDATE characters SET talent_key=? WHERE id=?", (talent_key, char['id']))
        char['talent_key'] = talent_key
        send_system_mail(char['id'], '机缘传承', f"你于打坐中偶得一段传承,自此身负{TALENTS[talent_key]['label']}之能。")
        notices.append(f"觅得{TALENTS[talent_key]['label']}")
    if not char['immortal_bone_key']:
        claimed = {r['immortal_bone_key'] for r in q(
            "SELECT immortal_bone_key FROM characters WHERE immortal_bone_key IS NOT NULL")}
        available = [k for k in IMMORTAL_BONE_MEDITATION_KEYS if k not in claimed]
        if available and random.random() < IMMORTAL_BONE_ROLL_CHANCE:
            bone_key = random.choice(available)
            run("UPDATE characters SET immortal_bone_key=? WHERE id=?", (bone_key, char['id']))
            char['immortal_bone_key'] = bone_key
            label = IMMORTAL_BONES[bone_key]['label']
            for c in q("SELECT id FROM characters"):
                send_system_mail(c['id'], '洗髓奇遇',
                                  f"{char['name']}打坐时触发洗髓奇遇,觅得旷世仙骨——{label},全宗独一份!",
                                  from_label='宗门公告')
            log_chronicle(f"{char['name']}({title_for(char['join_seq'], char['gender'])})于打坐中觅得{label}", major=True)
            notices.append(f"觅得仙骨——{label}")
    if char['rank_tier'] >= 2:
        owned_keys = {r['technique_key'] for r in q(
            "SELECT technique_key FROM character_techniques WHERE char_id=?", (char['id'],))}
        learnable = [k for k in PEAK_TECHNIQUES_BY_KEY if k not in owned_keys]
        roll_chance = TECHNIQUE_INHERITANCE_ROLL_CHANCE * (
            TECHNIQUE_INHERITANCE_ELDER_MULT if char['rank_tier'] >= 5 else 1)
        if learnable and random.random() < roll_chance:
            new_key = random.choice(learnable)
            run("INSERT INTO character_techniques (char_id,technique_key,learned_ts,mastery) VALUES (?,?,?,0)",
                (char['id'], new_key, now_ts()))
            new_label = PEAK_TECHNIQUES_BY_KEY[new_key]['label']
            send_system_mail(char['id'], '功法机缘', f"你于打坐中忽有所悟,习得旁门功法——{new_label}。")
            notices.append(f"习得功法——{new_label}")
    if not spirit_sense_unlocked(char['realm_idx']):
        lingjue = roll_lingjue_text(mind_state_band(char['mind_state'])['label'])
        if lingjue:
            notices.append(lingjue)
    if char['realm_idx'] >= SPIRIT_ROOT_ASCENSION_MIN_REALM and random.random() < SPIRIT_ROOT_ASCENSION_CHANCE:
        new_root = next_spirit_root(char['spirit_root'])
        if new_root:
            current_elements = (char['spirit_root_elements'] or '').split(',') if char['spirit_root_elements'] else []
            new_elements = next_spirit_root_elements(current_elements, new_root)
            run("UPDATE characters SET spirit_root=?, spirit_root_elements=? WHERE id=?",
                (new_root, ','.join(new_elements) if new_elements else None, char['id']))
            char['spirit_root'] = new_root
            char['spirit_root_elements'] = ','.join(new_elements) if new_elements else None
            root_label = spirit_root_label(new_root)
            notices.append(f"灵根蜕变——{root_label}")
            if char['equipped_weapon_key']:
                weapon_tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(char['equipped_weapon_key'])
                if weapon_tpl and not _weapon_usable(char, weapon_tpl):
                    _equip_item_silent(char, 'weapon', None)
                    notices.append(f"灵根蜕变后属性不再相合,「{weapon_tpl['label']}」已自动卸下放回行囊")
            if new_root == 'heaven':
                title = title_for(char['join_seq'], char['gender'])
                for c in q("SELECT id FROM characters"):
                    send_system_mail(c['id'], '灵根蜕变',
                                      f"{char['name']}({title})打坐间灵根悄然蜕变,一举踏入天灵根之境,全宗震动!",
                                      from_label='宗门公告')
                log_chronicle(f"{char['name']}({title})灵根蜕变至天灵根", major=True)
            else:
                send_system_mail(char['id'], '灵根蜕变', f"打坐间你忽觉体内灵根隐隐蜕变,由此踏入{root_label}之境!")

    # ── 修为/贡献结算:灵根倍率+打坐方式倍率(乘) + 师徒/血脉传承/仙骨/心境加成(百分比) ──
    root_mult = SPIRIT_ROOTS.get(char['spirit_root'], {}).get('mult', 1.0)
    band = mind_state_band(char['mind_state'])
    exp_pct = band['exp_pct']
    contribution_pct = 0
    exp_pct += dao_bonus(char['id'], 'exp_pct')
    if q("SELECT 1 FROM discipleships WHERE disciple_id=? AND status='active'", (char['id'],), one=True):
        exp_pct += MENTOR_EXP_BONUS_PCT
    exp_pct += bond_exp_bonus_pct(char['id'])
    specialty = get_peak_specialty(char)
    exp_pct += specialty.get('exp_bonus_pct', 0)
    if char['element_mutation']:
        exp_pct += ELEMENT_MUTATION_EXP_BONUS_PCT
    if char['equipped_pet_id']:
        equipped_pet_row = q("SELECT pet_key, level FROM character_pets WHERE id=?", (char['equipped_pet_id'],), one=True)
        if equipped_pet_row:
            pet = PET_TYPES[equipped_pet_row['pet_key']]
            pet_pct = pet_bonus_pct(equipped_pet_row['level'], equipped_pet_row['pet_key'])
            if pet['stat'] == 'exp':
                exp_pct += pet_pct + dao_bonus(char['id'], 'pet_pct')
            else:
                contribution_pct += pet_pct
    if char['talent_key']:
        pct, stat, _ = talent_stage_pct(char['talent_key'], char['realm_idx'])
        if stat == 'exp':
            exp_pct += pct
        else:
            contribution_pct += pct
    if char['immortal_bone_key']:
        bone = IMMORTAL_BONES[char['immortal_bone_key']]
        exp_pct += bone['exp_bonus_pct']
    if char['dan_quality']:
        exp_pct += DAN_QUALITIES[char['dan_quality']]['bonus']['exp_bonus_pct']
    if char['shen_quality']:
        exp_pct += SHEN_QUALITIES[char['shen_quality']]['bonus']['exp_bonus_pct']
    exp_pct -= technique_deviation_exp_penalty_pct(char['technique_deviation'])

    meditation_streak = S.get('meditation_streak', 0) if S.get('meditation_technique') == method else 0
    streak_bonus_pct = meditation_streak_bonus_pct(meditation_streak)
    exp_pct += streak_bonus_pct
    S['meditation_technique'] = method
    S['meditation_streak'] = meditation_streak + 1

    realm_mult = BASE_EXP_REALM_MULT.get(realm_major_idx(char['realm_idx']), 1)
    base_exp = random.randint(CULTIVATE_BASE_EXP_MIN, CULTIVATE_BASE_EXP_MAX) * realm_mult
    gained = round(base_exp * root_mult * cm['exp_mult'] * (1 + exp_pct / 100))
    contrib_gained = max(1, round((base_exp // 10) * (1 + contribution_pct / 100)))

    mind_delta = cm['mind_delta']
    epiphany = cm['epiphany_pct'] and random.random() < cm['epiphany_pct']
    if epiphany:
        gained *= 2
    if cm['mishap_pct'] and random.random() < cm['mishap_pct']:
        mind_delta -= 5

    if diminished:
        gained = round(gained * CULTIVATE_DIMINISH_MULT)
        contrib_gained = max(1, round(contrib_gained * CULTIVATE_DIMINISH_MULT))
    if in_severe_injury(char):
        gained = round(gained * TRAVEL_MINOR_INJURY_CULTIVATE_MULT)
        contrib_gained = max(1, round(contrib_gained * TRAVEL_MINOR_INJURY_CULTIVATE_MULT))
    bump_daily_counter(char['id'], 'cultivate_diminish')

    # 修为封顶在"下一个单级"的门槛,不能靠打坐把整个游戏的修为一次性攒够——
    # 必须先突破进下一级,才会解锁再往上攒的空间,逼着打坐/突破交替进行,不会前几天点完就再也用不上打坐了。
    capped = False
    if char['realm_idx'] < MAX_REALM_INDEX:
        room = REALMS[char['realm_idx'] + 1]['exp'] - char['exp']
        if gained >= room:
            gained = max(0, room)
            capped = True

    run("UPDATE characters SET exp=exp+?, contribution=contribution+?, total_contribution=total_contribution+?, "
        "mind_state=MAX(0,MIN(100,mind_state+?)) WHERE id=?",
        (gained, contrib_gained, contrib_gained, mind_delta, char['id']))

    if method in PEAK_TECHNIQUES_BY_KEY:
        add_dao_progress(char['id'], 'steadfast', daily_cap=5)
        mastery_gain = TECHNIQUE_MASTERY_EPIPHANY_GAIN if epiphany else TECHNIQUE_MASTERY_GAIN
        old_mastery = cm.get('mastery', 0)
        new_mastery = min(TECHNIQUE_MASTERY_MAX, old_mastery + mastery_gain)
        run("UPDATE character_techniques SET mastery=MIN(?,mastery+?) WHERE char_id=? AND technique_key=?",
            (TECHNIQUE_MASTERY_MAX, mastery_gain, char['id'], method))
        if old_mastery < TECHNIQUE_MASTERY_NEAR_PERFECT_LO <= new_mastery <= TECHNIQUE_MASTERY_NEAR_PERFECT_HI:
            notices.append(TECHNIQUE_MASTERY_NEAR_PERFECT_TEXT)
        if not _is_own_peak_technique(char, method) and cm.get('affinity_score', 100) < 50:
            run("UPDATE characters SET technique_deviation=MIN(?,technique_deviation+?) WHERE id=?",
                (TECHNIQUE_DEVIATION_MAX, TECHNIQUE_DEVIATION_GAIN, char['id']))

    mark_daily_task(char['id'], 'cultivate')
    check_achievements(char['id'])
    # 打坐之外的日常任务/成就奖励也可能顺带发修为,统一在这里再夹一道硬顶,
    # 保证"没突破就攒不到下一级门槛以上"这条规则不会被别的奖励渠道绕过去。
    if char['realm_idx'] < MAX_REALM_INDEX:
        run("UPDATE characters SET exp=MIN(exp,?) WHERE id=?",
            (REALMS[char['realm_idx'] + 1]['exp'], char['id']))
    # 用打坐结束后的真实DB值判断"是否已可突破",不能只看这次点击自己算出来的 gained——
    # 日常任务/成就奖励等其他渠道也可能顺带把修为推过门槛,消息得跟实际状态对得上。
    updated = q("SELECT exp,contribution,total_contribution,mind_state,stamina,realm_idx FROM characters WHERE id=?",
                (char['id'],), one=True)
    flavor = random.choice(CULTIVATE_FLAVORS.get(realm_major_idx(updated['realm_idx']), CULTIVATE_FLAVORS[0]))
    msg = f"{cm['label']}:{flavor},修为 +{gained}、贡献 +{contrib_gained}"
    if capped:
        msg += ',修为已抵瓶颈,需先突破方可再进'
    if diminished:
        msg += '(今日打坐已逾勤修之数,收益递减)'
    if epiphany:
        msg += ',顿悟降临,修为加倍!'
    if streak_bonus_pct:
        msg += f',入定渐深(连续{meditation_streak + 1}次,+{streak_bonus_pct}%)'
    if notices:
        msg += ' · ' + '、'.join(notices)
    ready_next = updated['realm_idx'] < MAX_REALM_INDEX and updated['exp'] >= REALMS[updated['realm_idx'] + 1]['exp']
    if ready_next:
        msg += ',修为已足,可前往静室后方尝试突破境界!'
    if request.accept_mimetypes.best == 'application/json':
        new_realm = realm_by_index(updated['realm_idx'])
        next_realm = REALMS[updated['realm_idx'] + 1] if updated['realm_idx'] < MAX_REALM_INDEX else None
        if next_realm:
            span = next_realm['exp'] - new_realm['exp']
            progress_pct = max(0, min(100, round((updated['exp'] - new_realm['exp']) / span * 100))) if span else 100
        else:
            progress_pct = 100
        return jsonify(
            ok=True, kind='cultivate', message=msg, rare=bool(epiphany or notices),
            epiphany=bool(epiphany), diminished=diminished, capped=capped, breakthrough_ready=ready_next,
            notices=notices, gained={'exp': gained, 'contribution': contrib_gained, 'mind': mind_delta},
            cooldown_base=CULTIVATE_COOLDOWN_SECONDS,
            stats={'exp': updated['exp'], 'contribution': updated['contribution'],
                   'total_contribution': updated['total_contribution'], 'mind': updated['mind_state'],
                   'stamina': updated['stamina'], 'realm': new_realm['name'],
                   'next_exp': next_realm['exp'] if next_realm else None, 'realm_progress': progress_pct})
    flash(msg, 'ok')
    return redirect(url_for('home'))

# ── 突破仪式:独立动作,修为攒够后手动触发,失败不扣修为、有连续失败保底 ────────────────

@app.route('/breakthrough')
@login_required
def breakthrough_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] == 5:
        return redirect(url_for('dan_home'))
    if char['realm_idx'] == 8:
        return redirect(url_for('infant_home'))
    if char['realm_idx'] == 11:
        return redirect(url_for('shen_home'))
    if char['realm_idx'] == 14:
        return redirect(url_for('heti_home'))
    char = sync_stamina(char)
    return render_template('breakthrough.html', char=char, event=None, **breakthrough_context(char))

def _breakthrough_pity_active(char):
    """化神起渡劫本就该比前面难,失败不再靠连败刷成功率,也没有连败必成的保底。"""
    return realm_major_idx(char['realm_idx']) < MAJOR_REALMS.index('化神')

def _breakthrough_chance(char, use_assist=False, guardian_bonus_pct=0):
    """最终成功率0~1。炼气等基础成功率已达100%的档位不受95%上限影响,不打折。"""
    band = mind_state_band(char['mind_state'])
    specialty = get_peak_specialty(char)
    bonus = (band['breakthrough_pct'] + dao_bonus(char['id'], 'breakthrough_pct')) / 100 + specialty.get('breakthrough_bonus_pct', 0) / 100
    if char['immortal_bone_key']:
        bonus += IMMORTAL_BONES[char['immortal_bone_key']]['breakthrough_bonus_pct'] / 100
    streak = char['breakthrough_fail_streak']
    pity_bonus = min(streak, BREAKTHROUGH_PITY_GUARANTEE_STREAK) * (BREAKTHROUGH_PITY_INCREMENT_PCT / 100) \
        if _breakthrough_pity_active(char) else 0
    assist_bonus = BREAKTHROUGH_ASSIST_BONUS_PCT / 100 if use_assist else 0
    base_chance = BREAKTHROUGH_CHANCE.get(realm_major_idx(char['realm_idx']), 0.2)
    if base_chance >= 1.0:
        return 1.0
    return min(0.95, base_chance + bonus + pity_bonus + assist_bonus + guardian_bonus_pct / 100)

def _available_guardians(char):
    """突破时可邀陪同的关系类型:师父/道侣/义结金兰/同峰同门,只看"是否有该关系",不点名具体某人。"""
    avail = {
        'mentor': bool(q("SELECT 1 FROM discipleships WHERE disciple_id=? AND status='active'",
                          (char['id'],), one=True)),
        'companion': bool(q("SELECT 1 FROM bonds WHERE bond_type='companion' AND status='active' "
                             "AND (char_a_id=? OR char_b_id=?)", (char['id'], char['id']), one=True)),
        'sworn': bool(q("SELECT 1 FROM bonds WHERE bond_type='sworn' AND status='active' "
                        "AND (char_a_id=? OR char_b_id=?)", (char['id'], char['id']), one=True)),
        'peer': bool(char['peak_id']) and bool(q(
            "SELECT 1 FROM characters WHERE peak_id=? AND id!=? AND ascended=0 AND deceased=0",
            (char['peak_id'], char['id']), one=True)),
    }
    return avail

def _breakthrough_stamina_cost(char):
    return max(1, BREAKTHROUGH_STAMINA_COST - cave_stability_stamina_discount(cave_stability(char)))

def breakthrough_context(char):
    realm = realm_by_index(char['realm_idx'])
    next_realm = REALMS[char['realm_idx'] + 1] if char['realm_idx'] < MAX_REALM_INDEX else None
    ready = bool(next_realm and char['exp'] >= next_realm['exp'])
    pity_active = _breakthrough_pity_active(char)
    streak = char['breakthrough_fail_streak'] if pity_active else 0
    guaranteed = streak >= BREAKTHROUGH_PITY_GUARANTEE_STREAK and pity_active
    chance_pct = None
    if ready and next_realm:
        chance_pct = 100 if guaranteed else round(_breakthrough_chance(char) * 100)
    avail = _available_guardians(char)
    guardian_options = [k for k in GUARDIAN_ORDER if avail.get(k)]
    return dict(realm=realm, next_realm=next_realm, ready=ready, streak=streak, guaranteed=guaranteed,
                chance_pct=chance_pct, stamina_cost=_breakthrough_stamina_cost(char),
                assist_cost=BREAKTHROUGH_ASSIST_CONTRIBUTION_COST, assist_bonus_pct=BREAKTHROUGH_ASSIST_BONUS_PCT,
                pity_guarantee_streak=BREAKTHROUGH_PITY_GUARANTEE_STREAK,
                pity_label=pity_stage_label(streak, BREAKTHROUGH_PITY_GUARANTEE_STREAK),
                guardian_options=guardian_options, guardian_types=GUARDIAN_TYPES)

@app.route('/breakthrough/attempt', methods=['POST'])
@login_required
def breakthrough_attempt():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] == 5:
        return redirect(url_for('dan_home'))
    if char['realm_idx'] == 8:
        return redirect(url_for('infant_home'))
    if char['realm_idx'] == 11:
        return redirect(url_for('shen_home'))
    if char['realm_idx'] == 14:
        return redirect(url_for('heti_home'))
    char = sync_stamina(char)
    next_realm = REALMS[char['realm_idx'] + 1] if char['realm_idx'] < MAX_REALM_INDEX else None
    if not next_realm or char['exp'] < next_realm['exp']:
        flash('修为尚不足以尝试突破', 'error')
        return redirect(url_for('breakthrough_home'))
    stamina_cost = _breakthrough_stamina_cost(char)
    if char['stamina'] < stamina_cost:
        flash('体力不足,无法尝试突破', 'error')
        return redirect(url_for('breakthrough_home'))
    use_assist = request.form.get('use_assist') == '1'
    if use_assist and char['contribution'] < BREAKTHROUGH_ASSIST_CONTRIBUTION_COST:
        flash('贡献不足,无法求援丹师辅助', 'error')
        return redirect(url_for('breakthrough_home'))
    guardian_type = request.form.get('guardian_type') or None
    if guardian_type and not _available_guardians(char).get(guardian_type):
        guardian_type = None  # 伪造的关系类型静默忽略,不值得为此打断突破流程
    guardian = GUARDIAN_TYPES.get(guardian_type)

    if use_assist and not _spend(char['id'], 'contribution', BREAKTHROUGH_ASSIST_CONTRIBUTION_COST):
        flash('贡献不足,无法求援丹师辅助', 'error')
        return redirect(url_for('breakthrough_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (stamina_cost, char['id']))

    streak = char['breakthrough_fail_streak']
    guaranteed = streak >= BREAKTHROUGH_PITY_GUARANTEE_STREAK and _breakthrough_pity_active(char)
    chance = _breakthrough_chance(char, use_assist, guardian['chance_bonus_pct'] if guardian else 0)
    success = guaranteed or random.random() <= chance

    if success:
        if guaranteed and streak:
            add_dao_progress(char['id'], 'defiance', amount=3)
        new_idx = char['realm_idx'] + 1
        run("UPDATE characters SET realm_idx=?, breakthrough_fail_streak=0 WHERE id=?", (new_idx, char['id']))
        old_major = realm_by_index(char['realm_idx'])['major']
        new_major = realm_by_index(new_idx)['major']
        title = title_for(char['join_seq'], char['gender'])
        if new_major != old_major:
            flavor = TRIBULATION_FLAVOR.get(new_major, '')
            log_chronicle(f"{char['name']}({title})突破至{new_major}期" + (f"——{flavor}" if flavor else ""),
                          major=MAJOR_REALMS.index(new_major) >= MAJOR_BROADCAST_MIN_IDX)
            if MAJOR_REALMS.index(new_major) >= MAJOR_BROADCAST_MIN_IDX:
                subject = '天劫异象' if new_major == '大乘' else '渡劫奇观'
                for c in q("SELECT id FROM characters"):
                    send_system_mail(c['id'], subject,
                                      f"{char['name']}于突破中{flavor}一举踏入{new_major}期!",
                                      from_label='宗门公告')
            if new_idx == MAX_REALM_INDEX:
                run("UPDATE characters SET dacheng_deadline_ts=?, dacheng_warned=0 WHERE id=?",
                    (now_ts() + DACHENG_ASCEND_DEADLINE_SECONDS, char['id']))
                send_system_mail(char['id'], '天劫将至', DACHENG_REACHED_FLAVOR, from_label='天道')
            if new_idx == SPIRIT_SENSE_UNLOCK_REALM_IDX:
                send_system_mail(char['id'], '入门指引·神识初成',
                                  '灵台清明,识海初开。此后探索秘境遇到妖物时,系统会按你的神识高低判定'
                                  '"识破"——识破了才看得到对方底细、首回合还能少挨点打。"智取"的成功率'
                                  '现在也看神识,不再是纯拼境界。这些数值都在首页身心状态卡片能看到,不需要特意去查。',
                                  from_label='宗门·执事堂')
                send_system_mail(char['id'], '入门指引·灵材与结丹',
                                  '筑基一途已过大半,金丹在望——但结丹不是修为攒够就能过,须先备齐灵材。'
                                  '灵材下品/中品/上品/极品怎么来:装备库藏里用不上的武器防具饰品可以分解换灵材;'
                                  '秘境探索(每日仅一次)会掉落地区专属材料,拿去材料仓库页兑换成对应品级的通用灵材;'
                                  '低阶灵材还能在材料仓库里合成成高阶(5个下品合1个中品,以此类推)。'
                                  '修为攒到筑基后期上限时,去静室的"结丹"入口备料渡劫即可。',
                                  from_label='宗门·执事堂')
        check_achievements(char['id'])
        if not guardian_type and not q("SELECT 1 FROM char_achievements WHERE char_id=? "
                                        "AND achievement_key='solo_breakthrough'", (char['id'],), one=True):
            d = q("SELECT * FROM achievement_defs WHERE key='solo_breakthrough'", one=True)
            if d:
                run("INSERT INTO char_achievements (char_id,achievement_key,achieved_ts) VALUES (?,?,?)",
                    (char['id'], 'solo_breakthrough', now_ts()))
                send_system_mail(char['id'], f"达成成就:{d['name']}", d['description'],
                                  attachment=json.loads(d['reward_json']))
        flash(f"突破成功!晋至 {REALMS[new_idx]['name']}" + ('(绝境顿悟!)' if guaranteed and streak else ''), 'ok')
        S['pending_result'] = {
            'ok': True, 'kind': 'breakthrough', 'rare': True, 'breakthrough': True,
            'message': f"晋至{REALMS[new_idx]['name']}" + ('(绝境顿悟!)' if guaranteed and streak else ''),
            'gained': {}, 'stats': {'realm': REALMS[new_idx]['name']},
        }
        return redirect(url_for('home'))

    mind_penalty = max(0, BREAKTHROUGH_FAIL_MIND_PENALTY
                       - (BREAKTHROUGH_ASSIST_MIND_PROTECT if use_assist else 0)
                       - (guardian['mind_protect'] if guardian else 0))
    run("UPDATE characters SET breakthrough_fail_streak=breakthrough_fail_streak+1, "
        "mind_state=MAX(0,mind_state-?) WHERE id=?", (mind_penalty, char['id']))
    add_dao_progress(char['id'], 'defiance', amount=1)
    char = me_character()
    if _breakthrough_pity_active(char):
        next_streak = char['breakthrough_fail_streak']
        stage = pity_stage_label(next_streak, BREAKTHROUGH_PITY_GUARANTEE_STREAK)
        hint = f",{stage},下次尝试必定突破!" if next_streak >= BREAKTHROUGH_PITY_GUARANTEE_STREAK else f",{stage},下次成功率大增"
    else:
        hint = ""
    demon_chance = MIND_DEMON_TRIGGER_CHANCE * (1 - cave_band_pct(cave_purity(char)) / 100)
    stability = spirit_sea_stability(char['mind_state'], char['technique_deviation'])
    if stability <= MIND_DEMON_TRIGGER_MIND_THRESHOLD and random.random() < demon_chance:
        avail = _available_guardians(char)
        has_bloodline = bool(char['talent_key'] and TALENTS[char['talent_key']]['source'] == 'bloodline')
        event = pick_mind_demon_event(avail['mentor'], avail['companion'], has_bloodline)
        flash('突破未成,心境大乱' + hint, 'error')
        return render_template('breakthrough.html', char=char, event=event, **breakthrough_context(char))
    flash('突破未成,修为分毫未损' + hint, 'error')
    return redirect(url_for('breakthrough_home'))

@app.route('/breakthrough/mind_demon', methods=['POST'])
@login_required
def breakthrough_mind_demon():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    event_key = request.form.get('event_key')
    choice_key = request.form.get('choice_key')
    event = MIND_DEMON_EVENTS_BY_KEY.get(event_key)
    choice = next((c for c in event['choices'] if c['key'] == choice_key), None) if event else None
    if not choice:
        flash('心魔已然消散', 'error')
        return redirect(url_for('breakthrough_home'))
    success = random.random() <= choice['success_rate']
    apply_reward(char['id'], choice['success'] if success else choice['fail'])
    flash('心魔已退,心境渐安' if success else '心魔未退,仍需静心调息', 'ok' if success else 'error')
    return redirect(url_for('breakthrough_home'))

# ── 凝丹:筑基→金丹取代常规突破,"选品质备料→渡劫"两段式,品质定终身、渡劫有保底 ────────

@app.route('/dan')
@login_required
def dan_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    ready = char['realm_idx'] == 5 and char['exp'] >= REALMS[6]['exp']
    chance_pct = None
    guaranteed = False
    if char['dan_stage'] == 1:
        streak = char['dan_fail_streak']
        chance_pct = round(dan_natural_chance(char['dan_quality_pending'], streak) * 100)
        guaranteed = streak >= DAN_PITY_GUARANTEE_STREAK
    upgrade_next = None
    if char['dan_quality']:
        idx = DAN_QUALITY_ORDER.index(char['dan_quality'])
        if idx < len(DAN_QUALITY_ORDER) - 1:
            upgrade_next = DAN_QUALITY_ORDER[idx + 1]
    return render_template('dan.html', char=char, ready=ready, chance_pct=chance_pct, guaranteed=guaranteed,
                            upgrade_next=upgrade_next, MATERIAL_LABELS=MATERIAL_LABELS,
                            owned=_materials_owned(char['id']),
                            DAN_QUALITIES=DAN_QUALITIES, DAN_QUALITY_ORDER=DAN_QUALITY_ORDER,
                            DAN_CORE_MATERIAL=DAN_CORE_MATERIAL, DAN_WARD_MATERIAL=DAN_WARD_MATERIAL,
                            DAN_FORTUNE_MATERIAL=DAN_FORTUNE_MATERIAL,
                            DAN_CORE_EXCHANGE=DAN_CORE_EXCHANGE, DAN_WARD_EXCHANGE=DAN_WARD_EXCHANGE,
                            DAN_CORE_CONTRIBUTION_COST=DAN_CORE_CONTRIBUTION_COST,
                            DAN_STAMINA_COST=DAN_STAMINA_COST, DAN_WARD_CHANCE_BONUS_PCT=DAN_WARD_CHANCE_BONUS_PCT,
                            DAN_UPGRADE_LINGSHI_COST=DAN_UPGRADE_LINGSHI_COST)

@app.route('/dan/exchange/<kind>', methods=['POST'])
@login_required
def dan_exchange(kind):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if kind not in ('core', 'ward'):
        flash('未知兑换类型', 'error')
        return redirect(url_for('dan_home'))
    ex = DAN_CORE_EXCHANGE if kind == 'core' else DAN_WARD_EXCHANGE
    target = DAN_CORE_MATERIAL if kind == 'core' else DAN_WARD_MATERIAL
    cost = {ex['from']: ex['rate']}
    if not _has_materials(char['id'], cost):
        flash(f"{MATERIAL_LABELS[ex['from']]}不足{ex['rate']}枚,无法兑换", 'error')
        return redirect(url_for('dan_home'))
    _consume_materials(char['id'], cost)
    _grant_material(char['id'], target, 1)
    flash(f"兑得{MATERIAL_LABELS[target]}×1", 'ok')
    return redirect(url_for('dan_home'))

@app.route('/dan/exchange_contribution', methods=['POST'])
@login_required
def dan_exchange_contribution():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['jindan_core_contrib_used']:
        flash('花贡献兑金丹引这条路,一辈子只能走一次,你已经用过了', 'error')
        return redirect(url_for('dan_home'))
    cur = run("UPDATE characters SET contribution=contribution-?, jindan_core_contrib_used=1 "
              "WHERE id=? AND contribution>=? AND jindan_core_contrib_used=0",
              (DAN_CORE_CONTRIBUTION_COST, char['id'], DAN_CORE_CONTRIBUTION_COST))
    if cur.rowcount == 0:
        flash(f"贡献不足{DAN_CORE_CONTRIBUTION_COST},无法兑换", 'error')
        return redirect(url_for('dan_home'))
    _grant_material(char['id'], DAN_CORE_MATERIAL, 1)
    flash(f"耗贡献{DAN_CORE_CONTRIBUTION_COST}兑得{MATERIAL_LABELS[DAN_CORE_MATERIAL]}×1(一辈子仅此一次,已用完)", 'ok')
    return redirect(url_for('dan_home'))

@app.route('/dan/prepare', methods=['POST'])
@login_required
def dan_prepare():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 5 or char['exp'] < REALMS[6]['exp']:
        flash('尚未至凝丹之时', 'error')
        return redirect(url_for('dan_home'))
    if char['dan_stage'] >= 1:
        flash('已选定品质,静候渡劫', 'error')
        return redirect(url_for('dan_home'))
    quality = request.form.get('quality')
    q_def = DAN_QUALITIES.get(quality)
    if not q_def:
        flash('请选择结丹品质', 'error')
        return redirect(url_for('dan_home'))
    if not _has_materials(char['id'], q_def['cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in q_def['cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('dan_home'))
    _consume_materials(char['id'], q_def['cost'])
    run("UPDATE characters SET dan_quality_pending=?, dan_stage=1 WHERE id=?", (quality, char['id']))
    flash(f"备料已成,{q_def['label']}胚基已定,可择日渡劫结丹", 'ok')
    return redirect(url_for('dan_home'))

@app.route('/dan/attempt', methods=['POST'])
@login_required
def dan_attempt():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 5 or char['dan_stage'] != 1:
        flash('尚未备料就绪', 'error')
        return redirect(url_for('dan_home'))
    char = sync_stamina(char)
    if char['stamina'] < DAN_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('dan_home'))
    use_ward = request.form.get('use_ward') == '1'
    if use_ward and not _has_materials(char['id'], {DAN_WARD_MATERIAL: 1}):
        flash('护丹符不足', 'error')
        return redirect(url_for('dan_home'))

    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (DAN_STAMINA_COST, char['id']))
    if use_ward:
        _consume_materials(char['id'], {DAN_WARD_MATERIAL: 1})

    q_def = DAN_QUALITIES[char['dan_quality_pending']]
    streak = char['dan_fail_streak']
    chance = dan_natural_chance(char['dan_quality_pending'], streak) + (
        DAN_WARD_CHANCE_BONUS_PCT / 100 if use_ward else 0)
    guaranteed = streak >= DAN_PITY_GUARANTEE_STREAK
    success = guaranteed or random.random() <= min(0.95, chance)

    if success:
        if guaranteed and streak:
            add_dao_progress(char['id'], 'defiance', amount=3)
        quality = char['dan_quality_pending']
        mutation = ELEMENT_MUTATIONS.get(char.get('element_mutation')) or {}
        dan_name = roll_dan_name(mutation.get('element'), char.get('artifact_core_orientation'))
        run("""UPDATE characters SET realm_idx=6, dan_quality=?, dan_name=?, dan_quality_pending=NULL, dan_stage=0,
               dan_fail_streak=0 WHERE id=?""", (quality, dan_name, char['id']))
        title = title_for(char['join_seq'], char['gender'])
        label = q_def['label']
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '凝丹圆满',
                              f"{char['name']}({title})历经磨砺,凝丹圆满,炼成{label}·{dan_name},晋入金丹之境!",
                              from_label='宗门公告')
        log_chronicle(f"{char['name']}({title})凝丹圆满,炼成{label}", major=True)
        check_achievements(char['id'])
        flash(f"{random.choice(DAN_SUCCESS_FLAVORS)}炼成{label}·{dan_name},晋入金丹初期", 'ok')
        return redirect(url_for('home'))

    run("UPDATE characters SET dan_fail_streak=dan_fail_streak+1, mind_state=MAX(0,mind_state-?) WHERE id=?",
        (DAN_FAIL_MIND_PENALTY, char['id']))
    add_dao_progress(char['id'], 'defiance', amount=1)
    next_streak = streak + 1
    hint = '下次必成!' if next_streak >= DAN_PITY_GUARANTEE_STREAK else '道心愈发凝练,下次成功率更高'
    flash(f"{random.choice(DAN_FAIL_FLAVORS)},{hint}", 'error')
    return redirect(url_for('dan_home'))

@app.route('/dan/upgrade', methods=['POST'])
@login_required
def dan_upgrade():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['dan_quality']:
        flash('尚未凝丹', 'error')
        return redirect(url_for('dan_home'))
    idx = DAN_QUALITY_ORDER.index(char['dan_quality'])
    if idx >= len(DAN_QUALITY_ORDER) - 1:
        flash('金丹品质已至巅峰', 'error')
        return redirect(url_for('dan_home'))
    next_quality = DAN_QUALITY_ORDER[idx + 1]
    q_def = DAN_QUALITIES[next_quality]
    if char['lingshi'] < DAN_UPGRADE_LINGSHI_COST:
        flash('灵石不足', 'error')
        return redirect(url_for('dan_home'))
    if not _has_materials(char['id'], q_def['cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in q_def['cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('dan_home'))
    if not _spend(char['id'], 'lingshi', DAN_UPGRADE_LINGSHI_COST):
        flash('灵石不足', 'error')
        return redirect(url_for('dan_home'))
    _consume_materials(char['id'], q_def['cost'])
    run("UPDATE characters SET dan_quality=? WHERE id=?", (next_quality, char['id']))
    flash(f"耗费重金,金丹升炼为{q_def['label']}!", 'ok')
    return redirect(url_for('dan_home'))

# ── 化婴:金丹→元婴取代常规突破,拆成"备料→心魔试炼→碎丹→渡雷劫"四段;前三段做完就锁定
# 进度,只有渡雷劫才是真正随机的关卡,失败也不会打回原形,调养后可再渡 ─────────────────

def _infant_tribulation_chance(char, use_ward=False):
    profile = _player_combat_profile(char)
    agility = profile['stats'].get('agility', 0)
    core_bonus_pct = char['artifact_core_level'] * INFANT_ARTIFACT_CORE_CHANCE_PER_LEVEL \
        if char['artifact_core_bound'] else 0
    streak = char['infant_fail_streak']
    chance = (INFANT_TRIBULATION_BASE_CHANCE + infant_pity_bonus_pct(streak) / 100
              + agility * INFANT_AGILITY_CHANCE_PER_POINT + core_bonus_pct / 100
              + (INFANT_TRIAL_BUFF_CHANCE_BONUS_PCT / 100 if char['infant_trial_buff'] else 0)
              + (INFANT_WARD_CHANCE_BONUS_PCT / 100 if use_ward else 0))
    return min(0.95, chance)

@app.route('/infant')
@login_required
def infant_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    weak = bool(char['infant_weak_until_ts'] and char['infant_weak_until_ts'] > now_ts())
    chance_pct = round(_infant_tribulation_chance(char) * 100) if char['infant_stage'] == 3 else None
    guaranteed = char['infant_fail_streak'] >= INFANT_PITY_GUARANTEE_STREAK
    return render_template('infant.html', char=char, weak=weak, chance_pct=chance_pct, guaranteed=guaranteed,
                            owned=_materials_owned(char['id']),
                            INFANT_CORE_CONTRIBUTION_COST=INFANT_CORE_CONTRIBUTION_COST,
                            weak_remaining=max(0, (char['infant_weak_until_ts'] or 0) - now_ts()),
                            REALMS=REALMS, MATERIAL_LABELS=MATERIAL_LABELS, INFANT_GATHER_COST=INFANT_GATHER_COST,
                            INFANT_CORE_MATERIAL=INFANT_CORE_MATERIAL, INFANT_WARD_MATERIAL=INFANT_WARD_MATERIAL,
                            INFANT_FORTUNE_MATERIAL=INFANT_FORTUNE_MATERIAL,
                            INFANT_CORE_EXCHANGE=INFANT_CORE_EXCHANGE, INFANT_WARD_EXCHANGE=INFANT_WARD_EXCHANGE,
                            INFANT_STAMINA_COST=INFANT_STAMINA_COST,
                            INFANT_WARD_CHANCE_BONUS_PCT=INFANT_WARD_CHANCE_BONUS_PCT,
                            INFANT_TRIAL_BOLD_MIND_COST=INFANT_TRIAL_BOLD_MIND_COST)

@app.route('/infant/exchange/<kind>', methods=['POST'])
@login_required
def infant_exchange(kind):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if kind not in ('core', 'ward'):
        flash('未知兑换类型', 'error')
        return redirect(url_for('infant_home'))
    ex = INFANT_CORE_EXCHANGE if kind == 'core' else INFANT_WARD_EXCHANGE
    target = INFANT_CORE_MATERIAL if kind == 'core' else INFANT_WARD_MATERIAL
    cost = {ex['from']: ex['rate']}
    if not _has_materials(char['id'], cost):
        flash(f"{MATERIAL_LABELS[ex['from']]}不足{ex['rate']}枚,无法兑换", 'error')
        return redirect(url_for('infant_home'))
    _consume_materials(char['id'], cost)
    _grant_material(char['id'], target, 1)
    flash(f"兑得{MATERIAL_LABELS[target]}×1", 'ok')
    return redirect(url_for('infant_home'))

@app.route('/infant/exchange_contribution', methods=['POST'])
@login_required
def infant_exchange_contribution():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['yuanying_core_contrib_used']:
        flash('花贡献兑元婴引这条路,一辈子只能走一次,你已经用过了', 'error')
        return redirect(url_for('infant_home'))
    cur = run("UPDATE characters SET contribution=contribution-?, yuanying_core_contrib_used=1 "
              "WHERE id=? AND contribution>=? AND yuanying_core_contrib_used=0",
              (INFANT_CORE_CONTRIBUTION_COST, char['id'], INFANT_CORE_CONTRIBUTION_COST))
    if cur.rowcount == 0:
        flash(f"贡献不足{INFANT_CORE_CONTRIBUTION_COST},无法兑换", 'error')
        return redirect(url_for('infant_home'))
    _grant_material(char['id'], INFANT_CORE_MATERIAL, 1)
    flash(f"耗贡献{INFANT_CORE_CONTRIBUTION_COST}兑得{MATERIAL_LABELS[INFANT_CORE_MATERIAL]}×1(一辈子仅此一次,已用完)", 'ok')
    return redirect(url_for('infant_home'))

@app.route('/infant/gather', methods=['POST'])
@login_required
def infant_gather():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 8 or char['exp'] < REALMS[9]['exp']:
        flash('尚未至化婴之时', 'error')
        return redirect(url_for('infant_home'))
    if char['infant_stage'] >= 1:
        flash('资源已备齐', 'error')
        return redirect(url_for('infant_home'))
    if not _has_materials(char['id'], INFANT_GATHER_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in INFANT_GATHER_COST.items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('infant_home'))
    _consume_materials(char['id'], INFANT_GATHER_COST)
    run("UPDATE characters SET infant_stage=1 WHERE id=?", (char['id'],))
    flash('化婴所需资源已备齐,可着手心魔试炼', 'ok')
    return redirect(url_for('infant_home'))

@app.route('/infant/trial/<choice>', methods=['POST'])
@login_required
def infant_trial(choice):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['infant_stage'] != 1:
        flash('尚未备齐资源', 'error')
        return redirect(url_for('infant_home'))
    if choice == 'bold':
        run("UPDATE characters SET infant_stage=2, infant_trial_buff=1, mind_state=MAX(0,mind_state-?) WHERE id=?",
            (INFANT_TRIAL_BOLD_MIND_COST, char['id']))
        flash('你直面心魔幻象,虽有所损耗,却也淬炼道心,渡劫时将更添几分把握', 'ok')
    elif choice == 'safe':
        run("UPDATE characters SET infant_stage=2 WHERE id=?", (char['id'],))
        flash('你静心以对,安然渡过此劫', 'ok')
    else:
        flash('请选择应对之法', 'error')
        return redirect(url_for('infant_home'))
    return redirect(url_for('infant_home'))

@app.route('/infant/shatter', methods=['POST'])
@login_required
def infant_shatter():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['infant_stage'] != 2:
        flash('尚未渡过心魔试炼', 'error')
        return redirect(url_for('infant_home'))
    run("UPDATE characters SET infant_stage=3 WHERE id=?", (char['id'],))
    flash('金丹破碎,元婴初凝,已无退路,只待渡过雷劫', 'ok')
    return redirect(url_for('infant_home'))

@app.route('/infant/tribulation', methods=['POST'])
@login_required
def infant_tribulation():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 8 or char['infant_stage'] != 3:
        flash('尚未至渡劫之时', 'error')
        return redirect(url_for('infant_home'))
    if char['infant_weak_until_ts'] and char['infant_weak_until_ts'] > now_ts():
        flash('元气尚虚,需先调养(服丹或静待恢复)', 'error')
        return redirect(url_for('infant_home'))
    char = sync_stamina(char)
    if char['stamina'] < INFANT_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('infant_home'))
    use_ward = request.form.get('use_ward') == '1'
    if use_ward and not _has_materials(char['id'], {INFANT_WARD_MATERIAL: 1}):
        flash('护婴符不足', 'error')
        return redirect(url_for('infant_home'))

    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (INFANT_STAMINA_COST, char['id']))
    if use_ward:
        _consume_materials(char['id'], {INFANT_WARD_MATERIAL: 1})

    streak = char['infant_fail_streak']
    guaranteed = streak >= INFANT_PITY_GUARANTEE_STREAK
    chance = _infant_tribulation_chance(char, use_ward=use_ward)
    success = guaranteed or random.random() <= chance

    if success:
        if guaranteed and streak:
            add_dao_progress(char['id'], 'defiance', amount=3)
        mutation = ELEMENT_MUTATIONS.get(char.get('element_mutation')) or {}
        infant_name = roll_infant_name(mutation.get('element'), char.get('artifact_core_orientation'))
        run("""UPDATE characters SET realm_idx=9, infant_name=?, infant_stage=0, infant_fail_streak=0,
               infant_trial_buff=0 WHERE id=?""", (infant_name, char['id']))
        title = title_for(char['join_seq'], char['gender'])
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '渡劫化婴',
                              f"{char['name']}({title})碎丹化婴,凝成{infant_name},晋入元婴之境!", from_label='宗门公告')
        log_chronicle(f"{char['name']}({title})渡劫化婴,晋入元婴", major=True)
        check_achievements(char['id'])
        flash(random.choice(INFANT_SUCCESS_FLAVORS), 'ok')
        return redirect(url_for('home'))

    profile = _player_combat_profile(char)
    defense = profile['stats'].get('defense', 0)
    mitigation = min(INFANT_DEFENSE_MIND_MITIGATION_CAP_PCT, defense * INFANT_DEFENSE_MIND_MITIGATION_PER_POINT)
    mind_penalty = round(INFANT_FAIL_MIND_PENALTY * (1 - mitigation / 100))
    run("""UPDATE characters SET infant_fail_streak=infant_fail_streak+1, infant_trial_buff=0,
           mind_state=MAX(0,mind_state-?), infant_weak_until_ts=? WHERE id=?""",
        (mind_penalty, now_ts() + INFANT_FAIL_WEAKEN_HOURS * 3600, char['id']))
    add_dao_progress(char['id'], 'defiance', amount=1)
    next_streak = streak + 1
    hint = '下次必成!' if next_streak >= INFANT_PITY_GUARANTEE_STREAK else '劫后凝练,下次更有把握'
    flash(f"{random.choice(INFANT_FAIL_FLAVORS)},需调养{INFANT_FAIL_WEAKEN_HOURS}小时,{hint}", 'error')
    return redirect(url_for('infant_home'))

@app.route('/infant/recover', methods=['POST'])
@login_required
def infant_recover():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not (char['infant_weak_until_ts'] and char['infant_weak_until_ts'] > now_ts()):
        flash('并无虚弱之状', 'error')
        return redirect(url_for('infant_home'))
    cur = run("UPDATE characters SET lingshi=lingshi-?, infant_weak_until_ts=0 WHERE id=? AND lingshi>=?",
              (INFANT_RECOVER_LINGSHI_COST, char['id'], INFANT_RECOVER_LINGSHI_COST))
    if cur.rowcount == 0:
        flash('灵石不足', 'error')
        return redirect(url_for('infant_home'))
    flash('服丹调养,元气已然恢复,可再渡雷劫', 'ok')
    return redirect(url_for('infant_home'))

# ── 化神:元婴→化神同样取代常规突破,"选品级备料→渡劫"两段式,与凝丹同一个思路 ──────────

@app.route('/shen')
@login_required
def shen_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    ready = char['realm_idx'] == 11 and char['exp'] >= REALMS[12]['exp']
    chance_pct = None
    guaranteed = False
    if char['shen_stage'] == 1:
        streak = char['shen_fail_streak']
        base = SHEN_QUALITIES[char['shen_quality_pending']]['base_chance']
        chance_pct = round(min(0.95, base + shen_pity_bonus_pct(streak) / 100) * 100)
        guaranteed = streak >= SHEN_PITY_GUARANTEE_STREAK
    upgrade_next = None
    if char['shen_quality']:
        idx = SHEN_QUALITY_ORDER.index(char['shen_quality'])
        if idx < len(SHEN_QUALITY_ORDER) - 1:
            upgrade_next = SHEN_QUALITY_ORDER[idx + 1]
    return render_template('shen.html', char=char, ready=ready, chance_pct=chance_pct, guaranteed=guaranteed,
                            upgrade_next=upgrade_next, MATERIAL_LABELS=MATERIAL_LABELS,
                            SHEN_QUALITIES=SHEN_QUALITIES, SHEN_QUALITY_ORDER=SHEN_QUALITY_ORDER,
                            SHEN_CORE_MATERIAL=SHEN_CORE_MATERIAL, SHEN_WARD_MATERIAL=SHEN_WARD_MATERIAL,
                            SHEN_GATE_MATERIAL=SHEN_GATE_MATERIAL,
                            SHEN_CORE_EXCHANGE=SHEN_CORE_EXCHANGE, SHEN_WARD_EXCHANGE=SHEN_WARD_EXCHANGE,
                            SHEN_STAMINA_COST=SHEN_STAMINA_COST, SHEN_WARD_CHANCE_BONUS_PCT=SHEN_WARD_CHANCE_BONUS_PCT,
                            SHEN_UPGRADE_LINGSHI_COST=SHEN_UPGRADE_LINGSHI_COST)

@app.route('/shen/exchange/<kind>', methods=['POST'])
@login_required
def shen_exchange(kind):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if kind not in ('core', 'ward'):
        flash('未知兑换类型', 'error')
        return redirect(url_for('shen_home'))
    ex = SHEN_CORE_EXCHANGE if kind == 'core' else SHEN_WARD_EXCHANGE
    target = SHEN_CORE_MATERIAL if kind == 'core' else SHEN_WARD_MATERIAL
    cost = {ex['from']: ex['rate']}
    if not _has_materials(char['id'], cost):
        flash(f"{MATERIAL_LABELS[ex['from']]}不足{ex['rate']}枚,无法兑换", 'error')
        return redirect(url_for('shen_home'))
    _consume_materials(char['id'], cost)
    _grant_material(char['id'], target, 1)
    flash(f"兑得{MATERIAL_LABELS[target]}×1", 'ok')
    return redirect(url_for('shen_home'))

@app.route('/shen/prepare', methods=['POST'])
@login_required
def shen_prepare():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 11 or char['exp'] < REALMS[12]['exp']:
        flash('尚未至化神之时', 'error')
        return redirect(url_for('shen_home'))
    if char['shen_stage'] >= 1:
        flash('已选定品级,静候渡劫', 'error')
        return redirect(url_for('shen_home'))
    quality = request.form.get('quality')
    q_def = SHEN_QUALITIES.get(quality)
    if not q_def:
        flash('请选择化神品级', 'error')
        return redirect(url_for('shen_home'))
    if not _has_materials(char['id'], q_def['cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in q_def['cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('shen_home'))
    _consume_materials(char['id'], q_def['cost'])
    run("UPDATE characters SET shen_quality_pending=?, shen_stage=1 WHERE id=?", (quality, char['id']))
    flash(f"备料已成,{q_def['label']}根基已定,可择日渡劫化神", 'ok')
    return redirect(url_for('shen_home'))

@app.route('/shen/attempt', methods=['POST'])
@login_required
def shen_attempt():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 11 or char['shen_stage'] != 1:
        flash('尚未备料就绪', 'error')
        return redirect(url_for('shen_home'))
    char = sync_stamina(char)
    if char['stamina'] < SHEN_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('shen_home'))
    use_ward = request.form.get('use_ward') == '1'
    if use_ward and not _has_materials(char['id'], {SHEN_WARD_MATERIAL: 1}):
        flash('护神符不足', 'error')
        return redirect(url_for('shen_home'))

    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (SHEN_STAMINA_COST, char['id']))
    if use_ward:
        _consume_materials(char['id'], {SHEN_WARD_MATERIAL: 1})

    q_def = SHEN_QUALITIES[char['shen_quality_pending']]
    streak = char['shen_fail_streak']
    chance = q_def['base_chance'] + shen_pity_bonus_pct(streak) / 100 + (
        SHEN_WARD_CHANCE_BONUS_PCT / 100 if use_ward else 0)
    guaranteed = streak >= SHEN_PITY_GUARANTEE_STREAK
    success = guaranteed or random.random() <= min(0.95, chance)

    if success:
        if guaranteed and streak:
            add_dao_progress(char['id'], 'defiance', amount=3)
        quality = char['shen_quality_pending']
        run("""UPDATE characters SET realm_idx=12, shen_quality=?, shen_quality_pending=NULL, shen_stage=0,
               shen_fail_streak=0 WHERE id=?""", (quality, char['id']))
        title = title_for(char['join_seq'], char['gender'])
        label = q_def['label']
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '渡劫化神',
                              f"{char['name']}({title})神魂淬炼有成,炼成{label},晋入化神之境!",
                              from_label='宗门公告')
        log_chronicle(f"{char['name']}({title})渡劫化神,炼成{label}", major=True)
        check_achievements(char['id'])
        flash(f"{random.choice(SHEN_SUCCESS_FLAVORS)}炼成{label},晋入化神初期", 'ok')
        return redirect(url_for('home'))

    run("UPDATE characters SET shen_fail_streak=shen_fail_streak+1, mind_state=MAX(0,mind_state-?) WHERE id=?",
        (SHEN_FAIL_MIND_PENALTY, char['id']))
    add_dao_progress(char['id'], 'defiance', amount=1)
    next_streak = streak + 1
    hint = '下次必成!' if next_streak >= SHEN_PITY_GUARANTEE_STREAK else '神魂愈发凝练,下次成功率更高'
    flash(f"{random.choice(SHEN_FAIL_FLAVORS)},{hint}", 'error')
    return redirect(url_for('shen_home'))

@app.route('/shen/upgrade', methods=['POST'])
@login_required
def shen_upgrade():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['shen_quality']:
        flash('尚未化神', 'error')
        return redirect(url_for('shen_home'))
    idx = SHEN_QUALITY_ORDER.index(char['shen_quality'])
    if idx >= len(SHEN_QUALITY_ORDER) - 1:
        flash('化神品级已至巅峰', 'error')
        return redirect(url_for('shen_home'))
    next_quality = SHEN_QUALITY_ORDER[idx + 1]
    q_def = SHEN_QUALITIES[next_quality]
    if char['lingshi'] < SHEN_UPGRADE_LINGSHI_COST:
        flash('灵石不足', 'error')
        return redirect(url_for('shen_home'))
    if not _has_materials(char['id'], q_def['cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in q_def['cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('shen_home'))
    if not _spend(char['id'], 'lingshi', SHEN_UPGRADE_LINGSHI_COST):
        flash('灵石不足', 'error')
        return redirect(url_for('shen_home'))
    _consume_materials(char['id'], q_def['cost'])
    run("UPDATE characters SET shen_quality=? WHERE id=?", (next_quality, char['id']))
    flash(f"耗费重金,化神境界升炼为{q_def['label']}!", 'ok')
    return redirect(url_for('shen_home'))

# ── 合体:化神→合体沿用化婴那套"备料→试炼→融合→天劫"四段式;化神门槛秘境暂未建,材料仍从
# 葬剑遗址取(用量更大),作为过渡方案 ─────────────────────────────────────────────

def _heti_adult_children_count(char_id):
    return q("""SELECT COUNT(*) c FROM offspring WHERE alive=1 AND realm_idx>=?
                AND ((parent_a_kind='char' AND parent_a_id=?) OR (parent_b_kind='char' AND parent_b_id=?))""",
             (HETI_CHILD_ADULT_REALM_IDX, char_id, char_id), one=True)['c']

def _heti_tribulation_chance(char, use_ward=False):
    profile = _player_combat_profile(char)
    agility = profile['stats'].get('agility', 0)
    core_bonus_pct = char['artifact_core_level'] * HETI_ARTIFACT_CORE_CHANCE_PER_LEVEL \
        if char['artifact_core_bound'] else 0
    streak = char['heti_fail_streak']
    chance = (HETI_TRIBULATION_BASE_CHANCE + heti_pity_bonus_pct(streak) / 100
              + agility * HETI_AGILITY_CHANCE_PER_POINT + core_bonus_pct / 100
              + (HETI_TRIAL_BUFF_CHANCE_BONUS_PCT / 100 if char['heti_trial_buff'] else 0)
              + (HETI_WARD_CHANCE_BONUS_PCT / 100 if use_ward else 0))
    chance = min(0.95, chance)
    # 子嗣及冠及笄的加成在95%上限之外单独结算,不受该上限压制,但这一项本身封顶+20%
    child_bonus_pct = min(HETI_CHILD_ADULT_CHANCE_BONUS_MAX_PCT,
                           _heti_adult_children_count(char['id']) * HETI_CHILD_ADULT_CHANCE_BONUS_PCT)
    chance += child_bonus_pct / 100
    return min(1.0, chance)

@app.route('/heti')
@login_required
def heti_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    weak = bool(char['heti_weak_until_ts'] and char['heti_weak_until_ts'] > now_ts())
    chance_pct = round(_heti_tribulation_chance(char) * 100) if char['heti_stage'] == 4 else None
    guaranteed = char['heti_fail_streak'] >= HETI_PITY_GUARANTEE_STREAK
    adult_children = _heti_adult_children_count(char['id'])
    lingzhu_count = _material_qty(char['id'], 'lingzhu_bead') if char['heti_stage'] == 1 else 0
    lingzhu_entries_used = q("SELECT COUNT(*) c FROM mystic_sessions WHERE char_id=? AND zone_key='lingzhu'",
                              (char['id'],), one=True)['c']
    return render_template('heti.html', char=char, weak=weak, chance_pct=chance_pct, guaranteed=guaranteed,
                            adult_children=adult_children,
                            child_bonus_pct=min(HETI_CHILD_ADULT_CHANCE_BONUS_MAX_PCT,
                                                 adult_children * HETI_CHILD_ADULT_CHANCE_BONUS_PCT),
                            lingzhu_count=lingzhu_count, lingzhu_required=HETI_LINGZHU_REQUIRED,
                            lingzhu_entries_used=lingzhu_entries_used,
                            lingzhu_entries_max=HETI_LINGZHU_MAX_ENTRIES,
                            weak_remaining=max(0, (char['heti_weak_until_ts'] or 0) - now_ts()),
                            REALMS=REALMS, MATERIAL_LABELS=MATERIAL_LABELS, HETI_GATHER_COST=HETI_GATHER_COST,
                            HETI_CORE_MATERIAL=HETI_CORE_MATERIAL, HETI_WARD_MATERIAL=HETI_WARD_MATERIAL,
                            HETI_CORE_EXCHANGE=HETI_CORE_EXCHANGE, HETI_WARD_EXCHANGE=HETI_WARD_EXCHANGE,
                            HETI_STAMINA_COST=HETI_STAMINA_COST,
                            HETI_WARD_CHANCE_BONUS_PCT=HETI_WARD_CHANCE_BONUS_PCT,
                            HETI_TRIAL_BOLD_MIND_COST=HETI_TRIAL_BOLD_MIND_COST,
                            HETI_RECOVER_LINGSHI_COST=HETI_RECOVER_LINGSHI_COST)

@app.route('/heti/exchange/<kind>', methods=['POST'])
@login_required
def heti_exchange(kind):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if kind not in ('core', 'ward'):
        flash('未知兑换类型', 'error')
        return redirect(url_for('heti_home'))
    cost = HETI_CORE_EXCHANGE if kind == 'core' else HETI_WARD_EXCHANGE
    target = HETI_CORE_MATERIAL if kind == 'core' else HETI_WARD_MATERIAL
    if not _has_materials(char['id'], cost):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in cost.items())
        flash(f"{cost_desc}不足,无法兑换", 'error')
        return redirect(url_for('heti_home'))
    _consume_materials(char['id'], cost)
    _grant_material(char['id'], target, 1)
    flash(f"兑得{MATERIAL_LABELS[target]}×1", 'ok')
    return redirect(url_for('heti_home'))

@app.route('/heti/gather', methods=['POST'])
@login_required
def heti_gather():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 14 or char['exp'] < REALMS[15]['exp']:
        flash('尚未至合体之时', 'error')
        return redirect(url_for('heti_home'))
    if char['heti_stage'] >= 1:
        flash('资源已备齐', 'error')
        return redirect(url_for('heti_home'))
    if not _has_materials(char['id'], HETI_GATHER_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in HETI_GATHER_COST.items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('heti_home'))
    _consume_materials(char['id'], HETI_GATHER_COST)
    run("UPDATE characters SET heti_stage=1 WHERE id=?", (char['id'],))
    flash('合体所需资源已备齐,神魂已自行开辟出灵珠秘境,可入内一探', 'ok')
    return redirect(url_for('heti_home'))

@app.route('/heti/lingzhu/advance', methods=['POST'])
@login_required
def heti_lingzhu_advance():
    """灵珠秘境:凑齐 HETI_LINGZHU_REQUIRED 颗灵珠即可离开此境,踏入本我试炼——此后灵珠秘境便再进不去了。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['heti_stage'] != 1:
        flash('尚不到灵珠秘境这一环节', 'error')
        return redirect(url_for('heti_home'))
    active_session = _mystic_session_today(char['id'])
    if active_session and active_session['status'] == 'active':
        flash('灵珠秘境的这一场探索尚未了结,先了结手头这场', 'error')
        return redirect(url_for('mystic_home'))
    if not _has_materials(char['id'], {'lingzhu_bead': HETI_LINGZHU_REQUIRED}):
        flash(f"灵珠尚不足{HETI_LINGZHU_REQUIRED}颗,需继续入灵珠秘境探寻", 'error')
        return redirect(url_for('heti_home'))
    _consume_materials(char['id'], {'lingzhu_bead': HETI_LINGZHU_REQUIRED})
    run("UPDATE characters SET heti_stage=2 WHERE id=?", (char['id'],))
    flash(f"{HETI_LINGZHU_REQUIRED}颗灵珠凝聚归位,灵珠秘境自行崩解,可着手本我试炼", 'ok')
    return redirect(url_for('heti_home'))

@app.route('/heti/trial/<choice>', methods=['POST'])
@login_required
def heti_trial(choice):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['heti_stage'] != 2:
        flash('尚未渡过灵珠秘境', 'error')
        return redirect(url_for('heti_home'))
    if choice == 'bold':
        run("UPDATE characters SET heti_stage=3, heti_trial_buff=1, mind_state=MAX(0,mind_state-?) WHERE id=?",
            (HETI_TRIAL_BOLD_MIND_COST, char['id']))
        flash('你直面本我与真我的交锋,虽有所损耗,却也淬炼道心,融合时将更添几分把握', 'ok')
    elif choice == 'safe':
        run("UPDATE characters SET heti_stage=3 WHERE id=?", (char['id'],))
        flash('你静心以对,安然渡过此劫', 'ok')
    else:
        flash('请选择应对之法', 'error')
        return redirect(url_for('heti_home'))
    return redirect(url_for('heti_home'))

@app.route('/heti/fuse', methods=['POST'])
@login_required
def heti_fuse():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['heti_stage'] != 3:
        flash('尚未渡过本我试炼', 'error')
        return redirect(url_for('heti_home'))
    run("UPDATE characters SET heti_stage=4 WHERE id=?", (char['id'],))
    flash('神魔初融,已无退路,只待渡过天劫', 'ok')
    return redirect(url_for('heti_home'))

@app.route('/heti/tribulation', methods=['POST'])
@login_required
def heti_tribulation():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] != 14 or char['heti_stage'] != 4:
        flash('尚未至渡劫之时', 'error')
        return redirect(url_for('heti_home'))
    if char['heti_weak_until_ts'] and char['heti_weak_until_ts'] > now_ts():
        flash('元气尚虚,需先调养(服丹或静待恢复)', 'error')
        return redirect(url_for('heti_home'))
    char = sync_stamina(char)
    if char['stamina'] < HETI_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('heti_home'))
    use_ward = request.form.get('use_ward') == '1'
    if use_ward and not _has_materials(char['id'], {HETI_WARD_MATERIAL: 1}):
        flash('合体护符不足', 'error')
        return redirect(url_for('heti_home'))

    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (HETI_STAMINA_COST, char['id']))
    if use_ward:
        _consume_materials(char['id'], {HETI_WARD_MATERIAL: 1})

    streak = char['heti_fail_streak']
    guaranteed = streak >= HETI_PITY_GUARANTEE_STREAK
    chance = _heti_tribulation_chance(char, use_ward=use_ward)
    success = guaranteed or random.random() <= chance

    if success:
        if guaranteed and streak:
            add_dao_progress(char['id'], 'defiance', amount=3)
        run("""UPDATE characters SET realm_idx=15, heti_stage=0, heti_fail_streak=0, heti_trial_buff=0
               WHERE id=?""", (char['id'],))
        title = title_for(char['join_seq'], char['gender'])
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '渡劫合体',
                              f"{char['name']}({title})神魔合体,历劫功成,晋入合体之境!", from_label='宗门公告')
        log_chronicle(f"{char['name']}({title})渡劫合体,晋入合体", major=True)
        check_achievements(char['id'])
        flash(random.choice(HETI_SUCCESS_FLAVORS), 'ok')
        return redirect(url_for('home'))

    profile = _player_combat_profile(char)
    defense = profile['stats'].get('defense', 0)
    mitigation = min(HETI_DEFENSE_MIND_MITIGATION_CAP_PCT, defense * HETI_DEFENSE_MIND_MITIGATION_PER_POINT)
    mind_penalty = round(HETI_FAIL_MIND_PENALTY * (1 - mitigation / 100))
    run("""UPDATE characters SET heti_fail_streak=heti_fail_streak+1, heti_trial_buff=0,
           mind_state=MAX(0,mind_state-?), heti_weak_until_ts=? WHERE id=?""",
        (mind_penalty, now_ts() + HETI_FAIL_WEAKEN_HOURS * 3600, char['id']))
    add_dao_progress(char['id'], 'defiance', amount=1)
    next_streak = streak + 1
    hint = '下次必成!' if next_streak >= HETI_PITY_GUARANTEE_STREAK else '劫后凝练,下次更有把握'
    flash(f"{random.choice(HETI_FAIL_FLAVORS)},需调养{HETI_FAIL_WEAKEN_HOURS}小时,{hint}", 'error')
    return redirect(url_for('heti_home'))

@app.route('/heti/recover', methods=['POST'])
@login_required
def heti_recover():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not (char['heti_weak_until_ts'] and char['heti_weak_until_ts'] > now_ts()):
        flash('并无虚弱之状', 'error')
        return redirect(url_for('heti_home'))
    cur = run("UPDATE characters SET lingshi=lingshi-?, heti_weak_until_ts=0 WHERE id=? AND lingshi>=?",
              (HETI_RECOVER_LINGSHI_COST, char['id'], HETI_RECOVER_LINGSHI_COST))
    if cur.rowcount == 0:
        flash('灵石不足', 'error')
        return redirect(url_for('heti_home'))
    flash('服丹调养,元气已然恢复,可再渡天劫', 'ok')
    return redirect(url_for('heti_home'))

# ── 飞升:大乘圆满起可主动举行,单次尝试失败不致命,可以随时再来——但天劫不会一直等,
# 大乘圆满起 DACHENG_ASCEND_DEADLINE_SECONDS 内必须渡劫成功,到期仍未飞升由 lifespan_tick()
# 惰性判定身陨(见 DACHENG_DEADLINE_DEATH_LABEL),不是失败了就没事,是拖到期限才没事。

@app.route('/ascend')
@login_required
def ascend_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    ready = char['realm_idx'] >= MAX_REALM_INDEX
    chance_pct = round(_ascension_chance(char) * 100) if ready else None
    avail = _available_guardians(char)
    guardian_options = [k for k in GUARDIAN_ORDER if avail.get(k)]
    deadline_remaining = max(0, char['dacheng_deadline_ts'] - now_ts()) if char['dacheng_deadline_ts'] else None
    return render_template('ascend.html', char=char, ready=ready, chance_pct=chance_pct,
                            stamina_cost=ASCENSION_STAMINA_COST, assist_cost=ASCENSION_ASSIST_CONTRIBUTION_COST,
                            assist_bonus_pct=ASCENSION_ASSIST_BONUS_PCT,
                            guardian_options=guardian_options, guardian_types=GUARDIAN_TYPES,
                            deadline_remaining=deadline_remaining)

def _ascension_chance(char, use_assist=False, guardian_bonus_pct=0):
    band = mind_state_band(char['mind_state'])
    bonus = band['breakthrough_pct'] / 100
    if char['immortal_bone_key']:
        bonus += IMMORTAL_BONES[char['immortal_bone_key']]['breakthrough_bonus_pct'] / 100
    if use_assist:
        bonus += ASCENSION_ASSIST_BONUS_PCT / 100
    bonus += guardian_bonus_pct / 100
    return min(0.95, ASCENSION_BASE_CHANCE + bonus)

@app.route('/ascend/attempt', methods=['POST'])
@login_required
def ascend_attempt():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    if char['realm_idx'] < MAX_REALM_INDEX:
        flash('尚未至大乘圆满,不到飞升之时', 'error')
        return redirect(url_for('ascend_home'))
    if char['stamina'] < ASCENSION_STAMINA_COST:
        flash('体力不足,难以支撑此等仪式', 'error')
        return redirect(url_for('ascend_home'))
    use_assist = request.form.get('use_assist') == '1'
    if use_assist and char['contribution'] < ASCENSION_ASSIST_CONTRIBUTION_COST:
        flash('贡献不足,无法求援护道', 'error')
        return redirect(url_for('ascend_home'))
    guardian_type = request.form.get('guardian_type') or None
    if guardian_type and not _available_guardians(char).get(guardian_type):
        guardian_type = None
    guardian = GUARDIAN_TYPES.get(guardian_type)

    dao_hao = request.form.get('dao_hao', '').strip()
    if dao_hao and not (1 <= len(dao_hao) <= 12):
        flash('道号长度需在 1-12 位之间', 'error')
        return redirect(url_for('ascend_home'))

    if use_assist and not _spend(char['id'], 'contribution', ASCENSION_ASSIST_CONTRIBUTION_COST):
        flash('贡献不足,无法求援护道', 'error')
        return redirect(url_for('ascend_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (ASCENSION_STAMINA_COST, char['id']))

    chance = _ascension_chance(char, use_assist, guardian['chance_bonus_pct'] if guardian else 0)
    success = random.random() <= chance

    if success:
        if dao_hao:
            run("UPDATE characters SET dao_hao=? WHERE id=?", (dao_hao, char['id']))
        claimed_offices = {r['celestial_office_key'] for r in
                            q("SELECT celestial_office_key FROM characters WHERE celestial_office_key IS NOT NULL")}
        pool = [k for k in CELESTIAL_OFFICES if k not in claimed_offices]
        candidates = random.sample(pool, min(5, len(pool)))
        run("UPDATE characters SET ascension_office_choices_json=? WHERE id=?",
            (json.dumps(candidates), char['id']))
        flash('天劫已渡,飞升在即!请先选定一方天庭神位,再正式证道飞升。', 'ok')
        return redirect(url_for('ascend_office_choose'))

    mind_penalty = max(0, ASCENSION_FAIL_MIND_PENALTY - (guardian['mind_protect'] if guardian else 0))
    run("UPDATE characters SET mind_state=MAX(0,mind_state-?) WHERE id=?", (mind_penalty, char['id']))
    flash('飞升未成,天劫暂歇,心神略有损耗,可随时再度尝试', 'error')
    return redirect(url_for('ascend_home'))

@app.route('/ascend/office')
@login_required
def ascend_office_choose():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    choices = json.loads(char['ascension_office_choices_json'] or '[]')
    if not choices:
        flash('尚无待选神位', 'error')
        return redirect(url_for('ascend_home'))
    return render_template('ascend_office.html', char=char, choices=choices, CELESTIAL_OFFICES=CELESTIAL_OFFICES)

@app.route('/ascend/office/<key>', methods=['POST'])
@login_required
def ascend_office_confirm(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    choices = json.loads(char['ascension_office_choices_json'] or '[]')
    if key not in choices or key not in CELESTIAL_OFFICES:
        flash('并非可选的神位', 'error')
        return redirect(url_for('ascend_office_choose'))
    if q("SELECT 1 FROM characters WHERE celestial_office_key=?", (key,), one=True):
        run("UPDATE characters SET ascension_office_choices_json=NULL WHERE id=?", (char['id'],))
        flash('这方神位刚被旁人占了,请重新发起飞升挑选', 'error')
        return redirect(url_for('ascend_home'))
    run("UPDATE characters SET celestial_office_key=?, ascension_office_choices_json=NULL WHERE id=?",
        (key, char['id']))
    title = title_for(char['join_seq'], char['gender'])
    retire_character(char['id'], 'ascended', f"{ASCENSION_FLAVOR}功成飞升,证道成仙")
    check_achievements(char['id'])
    dao_hao_note = f"从此道号「{char['dao_hao']}」," if char['dao_hao'] else ''
    office_note = f",拜授「{CELESTIAL_OFFICES[key]['label']}」一职"
    for c in q("SELECT id FROM characters WHERE id != ?", (char['id'],)):
        send_system_mail(c['id'], '飞升证道',
                          f"{char['name']}({title}){ASCENSION_FLAVOR}一举飞升,{dao_hao_note}"
                          f"{SECT_NAME}又添一位证道仙人{office_note}!",
                          from_label='宗门公告')
    flash(f"飞升成功!{ASCENSION_FLAVOR}{dao_hao_note}{office_note}", 'ok')
    return redirect(url_for('hall'))

# ── 天魔入侵:后台手动开启的限时活动,全宗共享同一头目血量,不是各打各的副本 ─────────────
# 没有后台定时任务,活动到期(24小时未剿灭)靠每次访问/攻击时惰性结算,跟寿元系统同一思路。
# 四阶段(降临/结阵/暴走/破魔)按血量比例自动推进,不是固定时长,详见 game_data.py 顶部注释。

def _invasion_latest():
    row = q("SELECT * FROM invasions ORDER BY id DESC LIMIT 1", one=True)
    return dict(row) if row else None

def _invasion_tier_reward(damage_dealt):
    reward = None
    for tier in INVASION_REWARD_TIERS:
        if damage_dealt >= tier['min_damage']:
            reward = tier['reward']
    return reward

def _invasion_distribute_rewards(invasion_id, mult=1.0):
    for p in q("SELECT * FROM invasion_participants WHERE invasion_id=? AND damage_dealt>0", (invasion_id,)):
        reward = _invasion_tier_reward(p['damage_dealt'])
        if not reward:
            continue
        apply_reward(p['char_id'], {k: round(v * mult) for k, v in reward.items()} if mult != 1.0 else reward)
        # 天魔饰品只在天魔被真正剿灭(mult==1.0)时发放,拖到过期(mult<1.0)不给——
        # 逼玩家真的合力打死头目,而不是躺着攒伤害等超时。
        if mult == 1.0 and p['damage_dealt'] >= INVASION_ACCESSORY_MIN_DAMAGE:
            _inventory_grant(p['char_id'], 'gear', 1, INVASION_ACCESSORY_KEY)
            char = q("SELECT name, join_seq, gender FROM characters WHERE id=?", (p['char_id'],), one=True)
            owner_title = title_for(char['join_seq'], char['gender'])
            send_system_mail(p['char_id'], '天魔饰品',
                              f"你力斩天魔,当次入侵累计伤害达{p['damage_dealt']},"
                              f"宗门特赐{INVASION_ACCESSORY_TEMPLATE['label']}一件!")
            log_chronicle(f"{char['name']}({owner_title})力斩天魔,伤害卓绝,获赠"
                          f"{INVASION_ACCESSORY_TEMPLATE['label']}", major=True)

def _invasion_resolve_expiry(inv):
    """惰性检查:活动早已到期却还没结算,这里顺手结算,不依赖后台定时任务。"""
    if inv['status'] != 'active' or now_ts() < inv['ends_ts']:
        return inv
    cur = run("UPDATE invasions SET status='expired', resolved_ts=? WHERE id=? AND status='active'",
              (now_ts(), inv['id']))
    if cur.rowcount:
        _invasion_distribute_rewards(inv['id'], mult=INVASION_EXPIRE_REWARD_MULT)
        for p in q("SELECT char_id FROM invasion_participants WHERE invasion_id=? AND damage_dealt>0", (inv['id'],)):
            send_system_mail(p['char_id'], '天魔遁走',
                              f"{INVASION_EXPIRED_FLAVOR}你曾出手迎战,宗门感念你的付出,略作犒赏。")
        log_chronicle(f"天魔入侵({inv['boss_label']})未能剿灭,天魔遁走", major=True)
    return q("SELECT * FROM invasions WHERE id=?", (inv['id'],), one=True)

def _invasion_check_phase(inv_id):
    """打完一次后重新读取boss_hp,按阈值推进phase(可能一次跨多个阈值);进入phase1时顺带生成魔将。"""
    inv = q("SELECT * FROM invasions WHERE id=?", (inv_id,), one=True)
    if not inv or inv['status'] != 'active':
        return inv
    hp_max = inv['boss_hp_max']
    ratio = inv['boss_hp'] / hp_max if hp_max else 0
    if ratio <= INVASION_PHASE_3_HP_RATIO:
        new_phase = 3
    elif ratio <= INVASION_PHASE_2_HP_RATIO:
        new_phase = 2
    elif ratio <= INVASION_PHASE_1_HP_RATIO:
        new_phase = 1
    else:
        new_phase = 0
    if new_phase != inv['phase']:
        if new_phase >= 1 and not inv['adds_json']:
            adds = {a['key']: {'label': a['label'], 'hp': round(hp_max * a['hp_ratio']),
                                'hp_max': round(hp_max * a['hp_ratio'])} for a in INVASION_ADDS}
            run("UPDATE invasions SET phase=?, adds_json=? WHERE id=? AND phase=?",
                (new_phase, json.dumps(adds), inv_id, inv['phase']))
        else:
            run("UPDATE invasions SET phase=? WHERE id=? AND phase=?", (new_phase, inv_id, inv['phase']))
    return q("SELECT * FROM invasions WHERE id=?", (inv_id,), one=True)

def _invasion_alive_adds(inv):
    if not inv['adds_json']:
        return {}
    return {k: v for k, v in json.loads(inv['adds_json']).items() if v['hp'] > 0}

@app.route('/invasion')
@login_required
def invasion_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    inv = _invasion_latest()
    if inv:
        inv = dict(_invasion_resolve_expiry(inv))
    my_row = None
    leaderboard = []
    adds = []
    killer = None
    if inv:
        my_row = q("SELECT * FROM invasion_participants WHERE invasion_id=? AND char_id=?",
                    (inv['id'], char['id']), one=True)
        leaderboard = q("""SELECT ip.damage_dealt, ip.attack_count, c.name, c.join_seq, c.gender
                            FROM invasion_participants ip JOIN characters c ON c.id = ip.char_id
                            WHERE ip.invasion_id=? ORDER BY ip.damage_dealt DESC LIMIT 10""", (inv['id'],))
        if inv['phase'] == 1 and inv['adds_json']:
            adds = [{'key': k, **v} for k, v in json.loads(inv['adds_json']).items()]
        if inv['killer_char_id']:
            killer = q("SELECT name, join_seq, gender FROM characters WHERE id=?", (inv['killer_char_id'],), one=True)
    attacks_today = get_daily_counter(char['id'], 'invasion_attack')
    return render_template('invasion.html', char=char, inv=inv, my_row=my_row, leaderboard=leaderboard,
                            adds=adds, killer=killer, now_ts=now_ts(),
                            attacks_today=attacks_today, INVASION_ATTACK_DAILY_LIMIT=INVASION_ATTACK_DAILY_LIMIT,
                            INVASION_PHASE_LABELS=INVASION_PHASE_LABELS,
                            INVASION_REWARD_TIERS=INVASION_REWARD_TIERS,
                            INVASION_ACCESSORY_MIN_DAMAGE=INVASION_ACCESSORY_MIN_DAMAGE,
                            INVASION_ACCESSORY_TEMPLATE=INVASION_ACCESSORY_TEMPLATE)

@app.route('/invasion/attack', methods=['POST'])
@login_required
def invasion_attack():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    inv = _invasion_latest()
    if not inv:
        flash('当前并无天魔入侵', 'error')
        return redirect(url_for('invasion_home'))
    inv = dict(_invasion_resolve_expiry(inv))
    if inv['status'] != 'active':
        flash('此次天魔入侵已经结束', 'error')
        return redirect(url_for('invasion_home'))
    if get_daily_counter(char['id'], 'invasion_attack') >= INVASION_ATTACK_DAILY_LIMIT:
        flash('今日讨魔次数已用完,明日再战', 'error')
        return redirect(url_for('invasion_home'))

    bump_daily_counter(char['id'], 'invasion_attack')
    profile = _player_combat_profile(char)
    raw_dmg = _discipline_simple_damage(
        profile, combat_damage(profile['stats']['attack'], 1.0, 0, char['realm_idx']))

    target = request.form.get('target', 'boss')
    alive_adds = _invasion_alive_adds(inv) if inv['phase'] == 1 else {}

    if inv['phase'] == 1 and target in alive_adds:
        path = f'$.{target}.hp'
        cur = run("""UPDATE invasions SET adds_json=json_set(adds_json,?,
                      MAX(0,json_extract(adds_json,?)-?)) WHERE id=? AND status='active'
                      AND json_extract(adds_json,?)>0""", (path, path, raw_dmg, inv['id'], path))
        if cur.rowcount == 0:
            flash('目标状态已变化,请重新查看', 'error')
            return redirect(url_for('invasion_home'))
        dmg_dealt = raw_dmg
        flash_prefix = random.choice(INVASION_ADD_ATTACK_FLAVORS).format(label=alive_adds[target]['label'])
    else:
        alive_count = len(alive_adds) if inv['phase'] == 1 else 0
        reduction = INVASION_ADD_SHIELD_MULT.get(alive_count, 1.0) if inv['phase'] == 1 else 1.0
        mult = INVASION_EXECUTE_DAMAGE_MULT if inv['phase'] == 3 else 1.0
        dmg_dealt = max(1, round(raw_dmg * reduction * mult))
        cur = run("UPDATE invasions SET boss_hp=MAX(0,boss_hp-?) WHERE id=? AND status='active'",
                  (dmg_dealt, inv['id']))
        if cur.rowcount == 0:
            flash('此次天魔入侵已经结束', 'error')
            return redirect(url_for('invasion_home'))
        flash_prefix = random.choice(INVASION_ATTACK_FLAVORS)

    run("""INSERT INTO invasion_participants (invasion_id,char_id,damage_dealt,attack_count) VALUES (?,?,?,1)
           ON CONFLICT(invasion_id,char_id) DO UPDATE SET damage_dealt=damage_dealt+excluded.damage_dealt,
           attack_count=attack_count+1""", (inv['id'], char['id'], dmg_dealt))
    weapon_mastery, weapon_level_up = _gain_weapon_mastery(char)

    backlash_msg = ''
    if inv['phase'] == 2 and random.random() < INVASION_BACKLASH_CHANCE:
        mitigation = min(INVASION_BACKLASH_MITIGATION_CAP_PCT,
                          profile['stats']['defense'] * INVASION_BACKLASH_DEFENSE_MITIGATION_PER_POINT)
        penalty = round(INVASION_BACKLASH_MIND_PENALTY * (1 - mitigation / 100))
        if penalty > 0:
            run("UPDATE characters SET mind_state=MAX(0,mind_state-?) WHERE id=?", (penalty, char['id']))
            backlash_msg = f",{INVASION_BACKLASH_FLAVOR},心境-{penalty}"

    updated_inv = _invasion_check_phase(inv['id'])
    remaining = max(0, updated_inv['boss_hp'])
    phase_label = INVASION_PHASE_LABELS[updated_inv['phase']]
    mastery_msg = ',' + _weapon_mastery_gain_text(weapon_mastery, weapon_level_up)
    flash(f"{flash_prefix}造成伤害 {dmg_dealt},天魔剩余气血 {remaining}/{updated_inv['boss_hp_max']}"
          f"({phase_label}){backlash_msg}{mastery_msg}", 'ok')

    if remaining <= 0:
        cur2 = run("UPDATE invasions SET status='defeated', resolved_ts=?, killer_char_id=? WHERE id=? AND status='active'",
                   (now_ts(), char['id'], inv['id']))
        if cur2.rowcount:
            _invasion_distribute_rewards(inv['id'])
            top = q("""SELECT c.id, c.name, c.join_seq, c.gender FROM invasion_participants ip
                       JOIN characters c ON c.id = ip.char_id WHERE ip.invasion_id=?
                       ORDER BY ip.damage_dealt DESC LIMIT 1""", (inv['id'],), one=True)
            top_title = title_for(top['join_seq'], top['gender'])
            killer_title = title_for(char['join_seq'], char['gender'])
            killer_line = (f"{char['name']}({killer_title})手起刀落,终结此劫!"
                            if char['id'] != top['id'] else '')
            for c in q("SELECT id FROM characters"):
                send_system_mail(c['id'], '天魔伏诛',
                                  f"{INVASION_DEFEATED_FLAVOR}{top['name']}({top_title})此役出力最多,居功至伟!"
                                  f"{killer_line}",
                                  from_label='宗门公告')
            log_chronicle(f"天魔入侵({inv['boss_label']})被合力剿灭,{top['name']}({top_title})居功至伟", major=True)
    return redirect(url_for('invasion_home'))

@app.route('/admin/invasion', methods=['GET', 'POST'])
@admin_required
def admin_invasion():
    last = _invasion_latest()
    cooldown_until = (last['opened_ts'] + INVASION_COOLDOWN_DAYS * 86400) if last else 0
    can_open = (not last) or (last['status'] != 'active' and now_ts() >= cooldown_until)
    if request.method == 'POST':
        if not can_open:
            flash('冷却尚未结束,或当前仍有进行中的天魔入侵', 'error')
            return redirect(url_for('admin_invasion'))
        boss_label = request.form.get('boss_label', '').strip() or '天魔·煞'
        hp_max = request.form.get('hp_max', type=int) or 200000
        hp_max = max(1, hp_max)
        run("""INSERT INTO invasions (status,boss_label,boss_hp,boss_hp_max,phase,opened_ts,ends_ts)
               VALUES ('active',?,?,?,0,?,?)""",
            (boss_label, hp_max, hp_max, now_ts(), now_ts() + INVASION_DURATION_HOURS * 3600))
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '天魔入侵',
                              f"{boss_label}破空降临,来势汹汹!前往迎战,合力将其击退——"
                              f"{INVASION_DURATION_HOURS}小时后若未能剿灭,天魔将自行遁走。",
                              from_label='宗门公告')
        log_chronicle(f"天魔入侵({boss_label})降临,宗门弟子合力迎战", major=True)
        log_admin('open_invasion', 'invasion', None, boss_label)
        flash('天魔入侵已开启', 'ok')
        return redirect(url_for('admin_invasion'))
    return render_template('admin/invasion.html', last=last, can_open=can_open, cooldown_until=cooldown_until,
                            now_ts=now_ts(), INVASION_DURATION_HOURS=INVASION_DURATION_HOURS,
                            INVASION_COOLDOWN_DAYS=INVASION_COOLDOWN_DAYS,
                            INVASION_PHASE_LABELS=INVASION_PHASE_LABELS)

@app.route('/admin/invasion/close', methods=['POST'])
@admin_required
def admin_invasion_close():
    inv = _invasion_latest()
    if inv and inv['status'] == 'active':
        cur = run("UPDATE invasions SET status='expired', resolved_ts=? WHERE id=? AND status='active'",
                  (now_ts(), inv['id']))
        if cur.rowcount:
            _invasion_distribute_rewards(inv['id'], mult=INVASION_EXPIRE_REWARD_MULT)
            log_admin('close_invasion', 'invasion', inv['id'], inv['boss_label'])
            flash('已手动结束当前天魔入侵', 'ok')
    else:
        flash('当前没有进行中的天魔入侵', 'error')
    return redirect(url_for('admin_invasion'))

# ── 宗门节日:后台选类型开启的轻量全宗活动,持续数日,到期访问时惰性结算并公布结果 ─────────

def _festival_latest():
    row = q("SELECT * FROM festivals ORDER BY id DESC LIMIT 1", one=True)
    return dict(row) if row else None

def _resolve_pet_show():
    """灵宠品鉴会六个类别的得主(只看各角色当前出战的那一只,不是名下所有灵宠都能参选);
    没人养灵宠就直接返回空,不硬凑名录。"""
    owners = [dict(r) for r in q("""
        SELECT characters.id, characters.name, characters.join_seq, characters.gender,
               character_pets.pet_key AS pet_key, character_pets.pet_name AS pet_name,
               character_pets.level AS pet_level, character_pets.bound_ts AS pet_bound_ts
        FROM characters JOIN character_pets ON character_pets.id = characters.equipped_pet_id
        WHERE characters.equipped_pet_id IS NOT NULL AND characters.ascended=0 AND characters.deceased=0""")]
    if not owners:
        return {}
    results = {}
    results['rarest'] = max(owners, key=lambda c: (
        PET_QUALITY_ORDER.index(PET_TYPES.get(c['pet_key'], {}).get('quality', 'low')), c['pet_level']))
    results['top_level'] = max(owners, key=lambda c: c['pet_level'])
    timed = [c for c in owners if c.get('pet_bound_ts')]
    if timed:
        results['longest'] = min(timed, key=lambda c: c['pet_bound_ts'])
    for key in ('appearance', 'history', 'popular'):
        results[key] = random.choice(owners)
    return results

def _resolve_kaishan(fest):
    """开山大典结算:按报名先后取出所有参与记录(line_text 是报名时就存好的一句史书文字)。"""
    return q("""SELECT kaishan_participation.*, characters.join_seq FROM kaishan_participation
                JOIN characters ON characters.id = kaishan_participation.char_id
                WHERE festival_id=? ORDER BY kaishan_participation.created_ts ASC""", (fest['id'],))

def _festival_resolve_expiry(fest):
    """惰性检查:节日早已到期却还没结算,这里顺手结算,不依赖后台定时任务。"""
    if fest['status'] != 'active' or now_ts() < fest['ends_ts']:
        return fest
    cur = run("UPDATE festivals SET status='resolved', resolved_ts=? WHERE id=? AND status='active'",
              (now_ts(), fest['id']))
    if cur.rowcount:
        results = {}
        lines = []
        if fest['type_key'] == 'pet_show':
            raw = _resolve_pet_show()
            for cat in PET_SHOW_CATEGORIES:
                char = raw.get(cat['key'])
                if not char:
                    continue
                title = title_for(char['join_seq'], char['gender'])
                pet_label = PET_TYPES.get(char['pet_key'], {}).get('label', '')
                results[cat['key']] = {'char_id': char['id'], 'name': char['name'], 'title': title,
                                        'pet_name': char['pet_name'], 'pet_label': pet_label, 'pet_key': char['pet_key']}
                apply_reward(char['id'], FESTIVAL_PET_SHOW_REWARD)
                lines.append(f"{cat['label']}——{char['name']}({title})的{char['pet_name'] or pet_label}")
        elif fest['type_key'] == 'kaishan':
            rows = _resolve_kaishan(fest)
            cfg = q("SELECT founded_ts FROM sect_config WHERE id=1", one=True)
            sect_year = game_year_of(fest['ends_ts'], cfg['founded_ts']) if cfg else 0
            history_lines = [r['line_text'] for r in rows]
            results = {'sect_year': sect_year, 'lines': history_lines,
                       'stage_idx': kaishan_stage_index(len(rows))}
            for r in rows:
                reward = dict(KAISHAN_DUTY_REWARD)
                if r['join_seq'] == 1:
                    reward = {k: round(v * KAISHAN_LEADER_REWARD_MULT) for k, v in reward.items()}
                apply_reward(r['char_id'], reward)
                send_system_mail(r['char_id'], f"开山大典·宗门{sect_year}年纪念",
                                  f"{r['line_text']}\n\n这段文字已录入宗门史册,与你共同留下这一届开山大典的记忆。",
                                  from_label='宗门公告')
            lines = [f"宗门{sect_year}年"] + history_lines
        elif fest['type_key'] == 'zhongqiu':
            rows = q("""SELECT * FROM zhongqiu_moments WHERE festival_id=? AND status='accepted'
                        ORDER BY responded_ts ASC""", (fest['id'],))
            moment_lines = [r['memory_text'] for r in rows if r['memory_text']]
            bake_stats = q("""SELECT COUNT(DISTINCT char_id) players,COALESCE(SUM(bake_count),0) baked
                              FROM zhongqiu_bake_collection WHERE festival_id=?""", (fest['id'],), one=True)
            bake_rankings = [dict(r) for r in q("""SELECT zhongqiu_bake_rankings.rank,characters.name,
                                      zhongqiu_bake_rankings.reward_lingshi
                               FROM zhongqiu_bake_rankings JOIN characters
                                 ON characters.id=zhongqiu_bake_rankings.char_id
                               WHERE festival_id=? ORDER BY rank""", (fest['id'],))]
            results = {'moments': moment_lines, 'bake_players': bake_stats['players'],
                       'bake_total': bake_stats['baked'], 'bake_rankings': bake_rankings}
            lines = moment_lines[:6]  # 落幕公告只摘前几条,不把所有人的回忆都塞进一封信
            if bake_rankings:
                lines.insert(0, '月饼大赛前三:' + '、'.join(f"{r['rank']}.{r['name']}" for r in bake_rankings))
        elif fest['type_key'] == 'xinsui':
            activity_rows = q("""SELECT * FROM xinsui_activity WHERE festival_id=?
                                  ORDER BY created_ts ASC""", (fest['id'],))
            for r in activity_rows:
                apply_reward(r['char_id'], XINSUI_ACTIVITY_REWARD)
            wish_rows = q("SELECT * FROM xinsui_wishes WHERE festival_id=?", (fest['id'],))
            for r in wish_rows:
                blessing_text = random.choice(XINSUI_WISH_BLESSINGS[r['wish_key']])
                apply_reward(r['char_id'], XINSUI_WISH_REWARD)
                send_system_mail(r['char_id'], '新岁赐福',
                                  f"新岁将至,宗门为你的「{XINSUI_WISHES[r['wish_key']]['label']}」之愿添一份福缘:{blessing_text}",
                                  from_label='宗门公告')
            activity_lines = [r['line_text'] for r in activity_rows]
            results = {'activity_lines': activity_lines, 'wish_count': len(wish_rows),
                       'stage_idx': xinsui_stage_index(len(activity_rows))}
            lines = activity_lines[:6]
        run("UPDATE festivals SET results_json=? WHERE id=?", (json.dumps(results), fest['id']))
        label = FESTIVAL_TYPES[fest['type_key']]['label']
        summary = '；'.join(lines) if lines else '本届圆满落幕'
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], f"{label}落幕", f"{label}圆满落幕!{summary}。", from_label='宗门公告')
        log_chronicle(f"{label}落幕:{summary}", major=True)
    return q("SELECT * FROM festivals WHERE id=?", (fest['id'],), one=True)

@app.route('/festival')
@login_required
def festival_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    results = json.loads(fest['results_json']) if fest and fest.get('results_json') else None
    kaishan_mine = None
    kaishan_count = 0
    kaishan_stage_idx = -1
    kaishan_draw_wait_min = 0
    kaishan_high_got = 0
    if fest and fest['type_key'] == 'kaishan' and fest['status'] == 'active':
        kaishan_mine = q("SELECT * FROM kaishan_participation WHERE festival_id=? AND char_id=?",
                          (fest['id'], char['id']), one=True)
        kaishan_count = q("SELECT COUNT(*) c FROM kaishan_participation WHERE festival_id=?",
                           (fest['id'],), one=True)['c']
        kaishan_stage_idx = kaishan_stage_index(kaishan_count)
        draw_row = q("SELECT last_draw_ts FROM kaishan_draws WHERE festival_id=? AND char_id=?",
                     (fest['id'], char['id']), one=True)
        if draw_row:
            elapsed = now_ts() - draw_row['last_draw_ts']
            if elapsed < KAISHAN_DRAW_COOLDOWN_SECONDS:
                kaishan_draw_wait_min = (KAISHAN_DRAW_COOLDOWN_SECONDS - elapsed + 59) // 60
        kaishan_high_got = _kaishan_high_total(char['id'])
    zhongqiu_mine = None
    zhongqiu_pending_in = []
    zhongqiu_pending_out = []
    zhongqiu_members = []
    zhongqiu_bake = None
    if fest and fest['type_key'] == 'zhongqiu' and fest['status'] == 'active':
        zhongqiu_mine = _zhongqiu_active_row(char['id'], fest['id'])
        zhongqiu_pending_in = q("""SELECT zhongqiu_moments.*, characters.name from_name FROM zhongqiu_moments
                                    JOIN characters ON characters.id = zhongqiu_moments.from_char_id
                                    WHERE zhongqiu_moments.festival_id=? AND zhongqiu_moments.to_char_id=?
                                    AND zhongqiu_moments.status='pending'""", (fest['id'], char['id']))
        zhongqiu_pending_out = q("""SELECT zhongqiu_moments.*, characters.name to_name FROM zhongqiu_moments
                                     JOIN characters ON characters.id = zhongqiu_moments.to_char_id
                                     WHERE zhongqiu_moments.festival_id=? AND zhongqiu_moments.from_char_id=?
                                     AND zhongqiu_moments.status='pending'""", (fest['id'], char['id']))
        if not zhongqiu_mine:
            zhongqiu_members = q("""SELECT id, name, join_seq, gender FROM characters
                                     WHERE ascended=0 AND deceased=0 AND is_npc=0 AND id!=?
                                     ORDER BY join_seq ASC""", (char['id'],))
        zhongqiu_bake = _zhongqiu_bake_context(char, fest)
    xinsui_wish_mine = None
    xinsui_activity_mine = None
    xinsui_activity_count = 0
    xinsui_stage_idx = -1
    xinsui_members = []
    xinsui_pending_blessings = []
    if fest and fest['type_key'] == 'xinsui' and fest['status'] == 'active':
        xinsui_wish_mine = q("SELECT * FROM xinsui_wishes WHERE festival_id=? AND char_id=?",
                              (fest['id'], char['id']), one=True)
        xinsui_activity_mine = q("SELECT * FROM xinsui_activity WHERE festival_id=? AND char_id=?",
                                  (fest['id'], char['id']), one=True)
        xinsui_activity_count = q("SELECT COUNT(*) c FROM xinsui_activity WHERE festival_id=?",
                                   (fest['id'],), one=True)['c']
        xinsui_stage_idx = xinsui_stage_index(xinsui_activity_count)
        xinsui_members = q("""SELECT id, name, join_seq, gender FROM characters
                               WHERE ascended=0 AND deceased=0 AND is_npc=0 AND id!=?
                               ORDER BY join_seq ASC""", (char['id'],))
    # 收到的福签不受当前节日类型/状态限制——可以是很久以前那届新岁赐福留下的,随时能回来拆。
    xinsui_pending_blessings = q("""SELECT xinsui_blessings.*, characters.name from_name FROM xinsui_blessings
                                     JOIN characters ON characters.id = xinsui_blessings.from_char_id
                                     WHERE xinsui_blessings.to_char_id=? AND xinsui_blessings.opened=0
                                     ORDER BY xinsui_blessings.created_ts ASC""", (char['id'],))
    return render_template('festival.html', char=char, fest=fest, results=results, now_ts=now_ts(),
                            FESTIVAL_TYPES=FESTIVAL_TYPES, PET_SHOW_CATEGORIES=PET_SHOW_CATEGORIES,
                            pet_image_url=pet_image_url,
                            KAISHAN_DUTIES=KAISHAN_DUTIES, KAISHAN_STAGES=KAISHAN_STAGES,
                            kaishan_mine=kaishan_mine, kaishan_count=kaishan_count,
                            kaishan_stage_idx=kaishan_stage_idx, leader=current_leader(),
                            ZHONGQIU_LOCATIONS=ZHONGQIU_LOCATIONS, ZHONGQIU_ACTIVITIES=ZHONGQIU_ACTIVITIES,
                            zhongqiu_mine=zhongqiu_mine, zhongqiu_pending_in=zhongqiu_pending_in,
                            zhongqiu_pending_out=zhongqiu_pending_out, zhongqiu_members=zhongqiu_members,
                            zhongqiu_bake=zhongqiu_bake, ZHONGQIU_MOONCAKES=ZHONGQIU_MOONCAKES,
                            ZHONGQIU_BAKE_RANK_REWARDS=ZHONGQIU_BAKE_RANK_REWARDS,
                            ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS=ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS,
                            title_for=title_for,
                            XINSUI_WISHES=XINSUI_WISHES, XINSUI_ACTIVITIES=XINSUI_ACTIVITIES,
                            XINSUI_STAGES=XINSUI_STAGES,
                            xinsui_wish_mine=xinsui_wish_mine, xinsui_activity_mine=xinsui_activity_mine,
                            xinsui_activity_count=xinsui_activity_count, xinsui_stage_idx=xinsui_stage_idx,
                            xinsui_members=xinsui_members, xinsui_pending_blessings=xinsui_pending_blessings,
                            MATERIAL_LABELS=MATERIAL_LABELS, kaishan_draw_wait_min=kaishan_draw_wait_min,
                            kaishan_high_got=kaishan_high_got, KAISHAN_HIGH_MATERIAL_CAP=KAISHAN_HIGH_MATERIAL_CAP)

def _kaishan_high_total(char_id):
    """上品材料封顶直接按仓库里现存的上品数量算,不额外记账——拿去凝丹等用途花掉了就不占额度了,
    也天然不会有"抽奖没留流水,历史对不上账"这种问题(领职责的一次性附赠同样体现在仓库现存量里)。"""
    return _material_qty(char_id, 'high')

def _kaishan_roll_material(high_remaining):
    """按 KAISHAN_MATERIAL_CHANCE 判定是否中奖;上品这一档受本届个人总量封顶——额度用完就从候选池里
    排除,不影响下品/中品照常抽(那两档不设总量限制)。中了就在对应品级数量上限内随机给一个数量,
    上品还会额外clamp到 high_remaining。未中奖返回 (None, None)。"""
    if random.random() >= KAISHAN_MATERIAL_CHANCE:
        return None, None
    tiers = [t for t in KAISHAN_MATERIAL_QTY_CAPS if t != 'high' or high_remaining > 0]
    weights = [KAISHAN_MATERIAL_TIER_WEIGHTS[t] for t in tiers]
    key = random.choices(tiers, weights=weights)[0]
    qty = random.randint(1, KAISHAN_MATERIAL_QTY_CAPS[key])
    if key == 'high':
        qty = min(qty, high_remaining)
    return key, qty

@app.route('/festival/kaishan/join', methods=['POST'])
@login_required
def kaishan_join():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'kaishan' or fest['status'] != 'active':
        flash('当前并无开山大典可参与', 'error')
        return redirect(url_for('festival_home'))
    duty_key = request.form.get('duty_key', '')
    if duty_key not in KAISHAN_DUTIES:
        flash('职责不存在', 'error')
        return redirect(url_for('festival_home'))
    if q("SELECT 1 FROM kaishan_participation WHERE festival_id=? AND char_id=?",
         (fest['id'], char['id']), one=True):
        flash('你已参与过本届开山大典了', 'error')
        return redirect(url_for('festival_home'))
    style = _weapon_style(char)
    name_label = f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
    line = kaishan_duty_line(duty_key, style, name_label)
    is_leader = char['join_seq'] == 1
    if is_leader:
        line += KAISHAN_LEADER_SUFFIX.format(title=title_for(1, char['gender']), name=char['name'])
    high_remaining = KAISHAN_HIGH_MATERIAL_CAP - _kaishan_high_total(char['id'])
    bonus_key, bonus_qty = _kaishan_roll_material(high_remaining)
    try:
        run("""INSERT INTO kaishan_participation (festival_id,char_id,duty_key,line_text,
               bonus_material_key,bonus_material_qty,created_ts) VALUES (?,?,?,?,?,?,?)""",
            (fest['id'], char['id'], duty_key, line, bonus_key, bonus_qty, now_ts()))
    except sqlite3.IntegrityError:
        flash('你已参与过本届开山大典了', 'error')
        return redirect(url_for('festival_home'))
    if bonus_key:
        _grant_material(char['id'], bonus_key, bonus_qty)
    count = q("SELECT COUNT(*) c FROM kaishan_participation WHERE festival_id=?", (fest['id'],), one=True)['c']
    new_stage = kaishan_stage_index(count)
    old_stage = kaishan_stage_index(count - 1)
    if new_stage > old_stage:
        stage = KAISHAN_STAGES[new_stage]
        text = stage['text'].format(leader=(current_leader()['name'] if current_leader() else '掌门'))
        log_chronicle(f"开山大典·{stage['label']}:{text}", major=True)
    msg = f"已领下「{KAISHAN_DUTIES[duty_key]['label']}」这份职责"
    if bonus_key:
        msg += f",辛苦有回报,额外得了{MATERIAL_LABELS[bonus_key]}×{bonus_qty}"
    flash(msg, 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/kaishan/draw', methods=['POST'])
@login_required
def kaishan_draw():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'kaishan' or fest['status'] != 'active':
        flash('当前并无开山大典可参与', 'error')
        return redirect(url_for('festival_home'))
    row = q("SELECT last_draw_ts FROM kaishan_draws WHERE festival_id=? AND char_id=?",
            (fest['id'], char['id']), one=True)
    if row and now_ts() - row['last_draw_ts'] < KAISHAN_DRAW_COOLDOWN_SECONDS:
        wait_min = (KAISHAN_DRAW_COOLDOWN_SECONDS - (now_ts() - row['last_draw_ts']) + 59) // 60
        flash(f"还需等{wait_min}分钟才能再抽一次", 'error')
        return redirect(url_for('festival_home'))
    high_remaining = KAISHAN_HIGH_MATERIAL_CAP - _kaishan_high_total(char['id'])
    bonus_key, bonus_qty = _kaishan_roll_material(high_remaining)
    run("""INSERT INTO kaishan_draws (festival_id,char_id,last_draw_ts) VALUES (?,?,?)
           ON CONFLICT(festival_id,char_id) DO UPDATE SET last_draw_ts=excluded.last_draw_ts""",
        (fest['id'], char['id'], now_ts()))
    if bonus_key:
        _grant_material(char['id'], bonus_key, bonus_qty)
        flash(f"典礼摸奖手气不错,得了{MATERIAL_LABELS[bonus_key]}×{bonus_qty}", 'ok')
    else:
        flash('这次摸奖空手而归,一小时后再来试试', 'ok')
    return redirect(url_for('festival_home'))

# ── 中秋观月:邀人赏月需对方回应,也可独自前往;每人本届限赏月一次(发起/接受都算用掉) ──

def _zhongqiu_active_row(char_id, festival_id):
    """本届是否已经"定下"了赏月(发起了未被拒绝的邀约/独自赏月/接受了他人的邀约)。"""
    return q("""SELECT * FROM zhongqiu_moments WHERE festival_id=?
                AND ((from_char_id=? AND status!='declined') OR (to_char_id=? AND status='accepted'))
                LIMIT 1""", (festival_id, char_id, char_id), one=True)

def _zhongqiu_bump_affinity(char_a_id, char_b_id, gain):
    bond = q("""SELECT * FROM bonds WHERE status='active' AND
                ((char_a_id=? AND char_b_id=?) OR (char_a_id=? AND char_b_id=?))""",
             (char_a_id, char_b_id, char_b_id, char_a_id), one=True)
    if bond:
        run("UPDATE bonds SET affinity=affinity+? WHERE id=?", (gain, bond['id']))

def _zhongqiu_festival():
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    return fest if fest and fest['type_key'] == 'zhongqiu' and fest['status'] == 'active' else None

def _zhongqiu_bake_context(char, fest):
    hour_bucket = now_ts() // 3600
    usage = q("""SELECT attempts_used FROM zhongqiu_bake_usage
                 WHERE festival_id=? AND char_id=? AND hour_bucket=?""",
              (fest['id'], char['id'], hour_bucket), one=True)
    session = q("SELECT * FROM zhongqiu_bake_sessions WHERE festival_id=? AND char_id=?",
                (fest['id'], char['id']), one=True)
    collection_rows = q("""SELECT cake_key,bake_count FROM zhongqiu_bake_collection
                           WHERE festival_id=? AND char_id=?""", (fest['id'], char['id']))
    inventory_rows = q("""SELECT cake_key,quantity FROM zhongqiu_mooncake_inventory
                          WHERE festival_id=? AND char_id=? AND quantity>0""", (fest['id'], char['id']))
    known_rows = q("""SELECT cake_key,known_steps FROM zhongqiu_bake_known
                      WHERE festival_id=? AND char_id=? AND known_steps>0""", (fest['id'], char['id']))
    rankings = q("""SELECT zhongqiu_bake_rankings.*,characters.name,characters.join_seq,characters.gender
                    FROM zhongqiu_bake_rankings JOIN characters ON characters.id=zhongqiu_bake_rankings.char_id
                    WHERE festival_id=? ORDER BY rank""", (fest['id'],))
    stats = q("""SELECT COUNT(DISTINCT char_id) players,COALESCE(SUM(bake_count),0) baked
                 FROM zhongqiu_bake_collection WHERE festival_id=?""", (fest['id'],), one=True)
    completed = {r['cake_key']: r['bake_count'] for r in collection_rows}
    inventory = {r['cake_key']: r['quantity'] for r in inventory_rows}
    known_steps_by_cake = {r['cake_key']: r['known_steps'] for r in known_rows}
    step_options = None
    if session:
        step_options = list(enumerate(ZHONGQIU_BAKE_STEPS[session['step_index']]))
        random.shuffle(step_options)
    return {
        'attempts_left': max(0, ZHONGQIU_BAKE_ATTEMPTS_PER_HOUR - (usage['attempts_used'] if usage else 0)),
        'next_attempt_ts': (hour_bucket + 1) * 3600,
        'session': session, 'step_options': step_options,
        'completed': completed, 'inventory': inventory, 'rankings': rankings,
        'known_steps_by_cake': known_steps_by_cake,
        'players': stats['players'] if stats else 0, 'baked': stats['baked'] if stats else 0,
        'members': q("""SELECT id,name,join_seq,gender FROM characters
                        WHERE ascended=0 AND deceased=0 AND is_npc=0 AND id!=? ORDER BY join_seq""", (char['id'],)),
    }

def _zhongqiu_finish_bake(fest, char, cake_key):
    """出炉结算:记入图鉴/月饼匣,集齐十味按名次发灵石奖励;返回名次提示文案(可能为空)。"""
    ts = now_ts()
    run("""INSERT INTO zhongqiu_bake_collection(festival_id,char_id,cake_key,first_baked_ts,bake_count)
           VALUES (?,?,?,?,1) ON CONFLICT(festival_id,char_id,cake_key) DO UPDATE SET bake_count=bake_count+1""",
        (fest['id'], char['id'], cake_key, ts))
    run("""INSERT INTO zhongqiu_mooncake_inventory(festival_id,char_id,cake_key,quantity)
           VALUES (?,?,?,1) ON CONFLICT(festival_id,char_id,cake_key) DO UPDATE SET quantity=quantity+1""",
        (fest['id'], char['id'], cake_key))
    count = q("SELECT COUNT(*) c FROM zhongqiu_bake_collection WHERE festival_id=? AND char_id=?",
              (fest['id'], char['id']), one=True)['c']
    rank_text = ''
    if count == len(ZHONGQIU_MOONCAKES):
        placed = q("SELECT COUNT(*) c FROM zhongqiu_bake_rankings WHERE festival_id=?", (fest['id'],), one=True)['c']
        rank = placed + 1
        if rank in ZHONGQIU_BAKE_RANK_REWARDS:
            reward = ZHONGQIU_BAKE_RANK_REWARDS[rank]
            try:
                run("INSERT INTO zhongqiu_bake_rankings VALUES (?,?,?,?,?)",
                    (fest['id'], char['id'], rank, ts, reward))
                apply_reward(char['id'], {'lingshi': reward})
                rank_text = f'，你是第{rank}位集齐十种月饼的弟子，获得{reward}灵石'
                if rank == 3:
                    shortened_ends = min(fest['ends_ts'], ts + ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS * 3600)
                    if shortened_ends < fest['ends_ts']:
                        run("UPDATE festivals SET ends_ts=? WHERE id=? AND ends_ts>?",
                            (shortened_ends, fest['id'], shortened_ends))
                        for member in q("SELECT id FROM characters WHERE ascended=0 AND deceased=0"):
                            send_system_mail(member['id'], '月饼大赛·三甲已定',
                                             f'十味先登榜三甲已全部产生，中秋观月将于{ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS}小时后提前落幕。',
                                             from_label='宗门公告')
                        rank_text += f'；三甲已定，活动进入{ZHONGQIU_BAKE_FINAL_COUNTDOWN_HOURS}小时收尾期'
            except sqlite3.IntegrityError:
                pass
    return rank_text

@app.route('/festival/zhongqiu/bake/start', methods=['POST'])
@login_required
def zhongqiu_bake_start():
    char = me_character()
    fest = _zhongqiu_festival()
    if not char or not fest:
        flash('当前并无中秋月饼大赛可参与', 'error')
        return redirect(url_for('festival_home'))
    cake_key = request.form.get('cake_key', '')
    if cake_key not in ZHONGQIU_MOONCAKES:
        flash('这种月饼不存在', 'error')
        return redirect(url_for('festival_home'))
    if q("SELECT 1 FROM zhongqiu_bake_sessions WHERE festival_id=? AND char_id=?",
         (fest['id'], char['id']), one=True):
        flash('炉中还有一枚月饼正在制作', 'error')
        return redirect(url_for('festival_home'))
    bucket = now_ts() // 3600
    cur = run("""INSERT INTO zhongqiu_bake_usage(festival_id,char_id,hour_bucket,attempts_used)
                 VALUES (?,?,?,1) ON CONFLICT(festival_id,char_id,hour_bucket) DO UPDATE
                 SET attempts_used=attempts_used+1 WHERE attempts_used<?""",
              (fest['id'], char['id'], bucket, ZHONGQIU_BAKE_ATTEMPTS_PER_HOUR))
    if cur.rowcount == 0:
        flash('这个时辰的三次开工机会已用完', 'error')
        return redirect(url_for('festival_home'))
    known_row = q("SELECT known_steps FROM zhongqiu_bake_known WHERE festival_id=? AND char_id=? AND cake_key=?",
                  (fest['id'], char['id'], cake_key), one=True)
    known_steps = known_row['known_steps'] if known_row else 0
    cake_name = ZHONGQIU_MOONCAKES[cake_key]['name']
    if known_steps >= len(ZHONGQIU_BAKE_STEPS):
        rank_text = _zhongqiu_finish_bake(fest, char, cake_key)
        flash(f"五道工序早已牢记于心，「{cake_name}」信手拈来，出炉成功，已收入月饼匣{rank_text}", 'ok')
        return redirect(url_for('festival_home'))
    run("""INSERT INTO zhongqiu_bake_sessions(festival_id,char_id,cake_key,step_index,started_ts)
           VALUES (?,?,?,?,?)""", (fest['id'], char['id'], cake_key, known_steps, now_ts()))
    hint = f"，前{known_steps}道工序已牢记于心，直接跳过" if known_steps else ""
    flash(f"已开始试做「{cake_name}」{hint}，请谨慎选择第{known_steps + 1}道工序", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/zhongqiu/bake/step', methods=['POST'])
@login_required
def zhongqiu_bake_step():
    char = me_character()
    fest = _zhongqiu_festival()
    if not char or not fest:
        return redirect(url_for('festival_home'))
    session = q("SELECT * FROM zhongqiu_bake_sessions WHERE festival_id=? AND char_id=?",
                (fest['id'], char['id']), one=True)
    choice = request.form.get('choice', type=int)
    if not session or choice not in range(4):
        flash('试炼进度不存在', 'error')
        return redirect(url_for('festival_home'))
    cake = ZHONGQIU_MOONCAKES[session['cake_key']]
    step = session['step_index']
    if choice != cake['recipe'][step]:
        run("DELETE FROM zhongqiu_bake_sessions WHERE festival_id=? AND char_id=?",
            (fest['id'], char['id']))
        flash(f"第{step + 1}道工序出错，月饼坏掉了，只能从头再来"
              + ('(前面已记熟的工序不会忘记)' if step else ''), 'error')
        return redirect(url_for('festival_home'))
    run("""INSERT INTO zhongqiu_bake_known(festival_id,char_id,cake_key,known_steps)
           VALUES (?,?,?,?)
           ON CONFLICT(festival_id,char_id,cake_key) DO UPDATE SET known_steps=MAX(known_steps, excluded.known_steps)""",
        (fest['id'], char['id'], session['cake_key'], step + 1))
    if step < 4:
        run("UPDATE zhongqiu_bake_sessions SET step_index=step_index+1 WHERE festival_id=? AND char_id=?",
            (fest['id'], char['id']))
        flash(f"第{step + 1}道工序正确，进入下一道", 'ok')
        return redirect(url_for('festival_home'))
    run("DELETE FROM zhongqiu_bake_sessions WHERE festival_id=? AND char_id=?", (fest['id'], char['id']))
    rank_text = _zhongqiu_finish_bake(fest, char, session['cake_key'])
    flash(f"「{cake['name']}」出炉成功，已收入月饼匣{rank_text}", 'ok')
    return redirect(url_for('festival_home'))

def _zhongqiu_take_mooncake(fest_id, char_id, cake_key):
    cur = run("""UPDATE zhongqiu_mooncake_inventory SET quantity=quantity-1
                 WHERE festival_id=? AND char_id=? AND cake_key=? AND quantity>0""",
              (fest_id, char_id, cake_key))
    return cur.rowcount > 0

@app.route('/festival/zhongqiu/mooncake/eat', methods=['POST'])
@login_required
def zhongqiu_mooncake_eat():
    char = me_character(); fest = _zhongqiu_festival()
    cake_key = request.form.get('cake_key', '')
    if not char or not fest or cake_key not in ZHONGQIU_MOONCAKES or not _zhongqiu_take_mooncake(fest['id'], char['id'], cake_key):
        flash('月饼匣里没有这枚月饼', 'error')
        return redirect(url_for('festival_home'))
    apply_reward(char['id'], {'mind_state': 2})
    flash(ZHONGQIU_MOONCAKES[cake_key]['eat_text'] + '（心境+2）', 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/zhongqiu/mooncake/gift', methods=['POST'])
@login_required
def zhongqiu_mooncake_gift():
    char = me_character(); fest = _zhongqiu_festival()
    cake_key = request.form.get('cake_key', '')
    to_char_id = request.form.get('to_char_id', type=int)
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0 AND is_npc=0",
               (to_char_id,), one=True) if to_char_id else None
    if not char or not fest or cake_key not in ZHONGQIU_MOONCAKES or not target or target['id'] == char['id']:
        flash('赠送对象或月饼不存在', 'error')
        return redirect(url_for('festival_home'))
    if not _zhongqiu_take_mooncake(fest['id'], char['id'], cake_key):
        flash('月饼匣里没有这枚月饼', 'error')
        return redirect(url_for('festival_home'))
    run("""INSERT INTO zhongqiu_mooncake_inventory(festival_id,char_id,cake_key,quantity)
           VALUES (?,?,?,1) ON CONFLICT(festival_id,char_id,cake_key) DO UPDATE SET quantity=quantity+1""",
        (fest['id'], target['id'], cake_key))
    cake_name = ZHONGQIU_MOONCAKES[cake_key]['name']
    send_system_mail(target['id'], '中秋月饼', f"{char['name']}将亲手做的「{cake_name}」送给了你，已收入月饼匣。")
    flash(f"已将「{cake_name}」送给{target['name']}", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/zhongqiu/solo', methods=['POST'])
@login_required
def zhongqiu_solo():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'zhongqiu' or fest['status'] != 'active':
        flash('当前并无中秋观月可参与', 'error')
        return redirect(url_for('festival_home'))
    location_key = request.form.get('location_key', '')
    activity_key = request.form.get('activity_key', '')
    if location_key not in ZHONGQIU_LOCATIONS or activity_key not in ZHONGQIU_ACTIVITIES:
        flash('地点或互动不存在', 'error')
        return redirect(url_for('festival_home'))
    if _zhongqiu_active_row(char['id'], fest['id']):
        flash('你本届已经赏过月了', 'error')
        return redirect(url_for('festival_home'))
    name_label = f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
    style = _weapon_style(char)
    gift_name = None
    gift_desc = None
    if activity_key == 'gift':
        gift = zhongqiu_gift_roll()
        gift_name = gift['name']
        gift_desc = f"{gift['name']}({GIFT_RARITIES[gift['rarity_key']]['label']}·{GIFT_TRAITS[gift['trait_key']]['label']})"
    line = zhongqiu_moon_line(activity_key, style, name_label, gift_name=gift_name,
                               location_key=location_key)
    try:
        run("""INSERT INTO zhongqiu_moments (festival_id,from_char_id,to_char_id,location_key,activity_key,
               status,memory_text,gift_desc,created_ts,responded_ts) VALUES (?,?,NULL,?,?,'accepted',?,?,?,?)""",
            (fest['id'], char['id'], location_key, activity_key, line, gift_desc, now_ts(), now_ts()))
    except sqlite3.IntegrityError:
        flash('你本届已经赏过月了', 'error')
        return redirect(url_for('festival_home'))
    apply_reward(char['id'], ZHONGQIU_REWARD)
    flash('你独自赏了一回月', 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/zhongqiu/invite', methods=['POST'])
@login_required
def zhongqiu_invite():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'zhongqiu' or fest['status'] != 'active':
        flash('当前并无中秋观月可参与', 'error')
        return redirect(url_for('festival_home'))
    to_char_id = request.form.get('to_char_id', type=int)
    location_key = request.form.get('location_key', '')
    activity_key = request.form.get('activity_key', '')
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0 AND is_npc=0",
               (to_char_id,), one=True) if to_char_id else None
    if not target or target['id'] == char['id']:
        flash('赏月对象不存在', 'error')
        return redirect(url_for('festival_home'))
    if location_key not in ZHONGQIU_LOCATIONS or activity_key not in ZHONGQIU_ACTIVITIES:
        flash('地点或互动不存在', 'error')
        return redirect(url_for('festival_home'))
    if _zhongqiu_active_row(char['id'], fest['id']):
        flash('你本届已经赏过月了', 'error')
        return redirect(url_for('festival_home'))
    try:
        run("""INSERT INTO zhongqiu_moments (festival_id,from_char_id,to_char_id,location_key,activity_key,
               status,created_ts) VALUES (?,?,?,?,?,'pending',?)""",
            (fest['id'], char['id'], target['id'], location_key, activity_key, now_ts()))
    except sqlite3.IntegrityError:
        flash('你本届已经赏过月了', 'error')
        return redirect(url_for('festival_home'))
    send_system_mail(target['id'], '中秋观月之邀',
                      f"{char['name']}邀你于{ZHONGQIU_LOCATIONS[location_key]['label']}共度中秋,"
                      f"一同{ZHONGQIU_ACTIVITIES[activity_key]['label']},请到「宗门节日」页回应。")
    flash(f"已向{target['name']}发出赏月之邀,等待对方回应", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/zhongqiu/<int:moment_id>/respond', methods=['POST'])
@login_required
def zhongqiu_respond(moment_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    moment = q("SELECT * FROM zhongqiu_moments WHERE id=? AND to_char_id=? AND status='pending'",
               (moment_id, char['id']), one=True)
    if not moment:
        flash('这份邀约不存在或已处理', 'error')
        return redirect(url_for('festival_home'))
    fest = q("SELECT * FROM festivals WHERE id=?", (moment['festival_id'],), one=True)
    if not fest or fest['status'] != 'active':
        flash('这届中秋观月已经落幕了', 'error')
        return redirect(url_for('festival_home'))
    action = request.form.get('action', '')
    if action == 'decline':
        cur = run("UPDATE zhongqiu_moments SET status='declined', responded_ts=? WHERE id=? AND status='pending'",
                  (now_ts(), moment_id))
        if cur.rowcount == 0:
            flash('这份邀约不存在或已处理', 'error')
            return redirect(url_for('festival_home'))
        send_system_mail(moment['from_char_id'], '赏月之邀', f"{char['name']}这次没能赴约赏月。")
        flash('已回绝这份邀约', 'ok')
        return redirect(url_for('festival_home'))
    if action != 'accept':
        flash('未知操作', 'error')
        return redirect(url_for('festival_home'))
    if _zhongqiu_active_row(char['id'], fest['id']):
        flash('你本届已经赏过月了', 'error')
        return redirect(url_for('festival_home'))
    inviter = q("SELECT * FROM characters WHERE id=?", (moment['from_char_id'],), one=True)
    inviter_label = f"{inviter['name']}({title_for(inviter['join_seq'], inviter['gender'])})"
    partner_label = f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
    style = _weapon_style(inviter)
    gift_name = None
    gift_desc = None
    if moment['activity_key'] == 'gift':
        gift = zhongqiu_gift_roll()
        gift_name = gift['name']
        gift_desc = f"{gift['name']}({GIFT_RARITIES[gift['rarity_key']]['label']}·{GIFT_TRAITS[gift['trait_key']]['label']})"
    line = zhongqiu_moon_line(moment['activity_key'], style, inviter_label, partner_label=partner_label,
                               gift_name=gift_name, location_key=moment['location_key'])
    cur = run("""UPDATE zhongqiu_moments SET status='accepted', memory_text=?, gift_desc=?, responded_ts=?
           WHERE id=? AND status='pending'""", (line, gift_desc, now_ts(), moment_id))
    if cur.rowcount == 0:
        flash('这份邀约不存在或已处理', 'error')
        return redirect(url_for('festival_home'))
    apply_reward(char['id'], ZHONGQIU_REWARD)
    apply_reward(inviter['id'], ZHONGQIU_REWARD)
    _zhongqiu_bump_affinity(char['id'], inviter['id'], ZHONGQIU_AFFINITY_GAIN)
    send_system_mail(inviter['id'], '赏月之邀', f"{char['name']}应约赴会,与你共度了一段中秋时光。\n\n{line}")
    flash('已赴约赏月', 'ok')
    return redirect(url_for('festival_home'))

# ── 新岁赐福:许愿(带上届回顾)+ 除岁活动(全宗共享进度,跟开山大典同一个思路)+ 福签/红包 ──

def _xinsui_snapshot_inputs(char):
    mastery_total = q("SELECT COALESCE(SUM(mastery),0) s FROM character_weapon_masteries WHERE char_id=?",
                       (char['id'],), one=True)['s']
    dan_idx = DAN_QUALITY_ORDER.index(char['dan_quality']) if char['dan_quality'] else -1
    has_companion = bool(q("""SELECT 1 FROM bonds WHERE status='active' AND bond_type='companion'
                              AND (char_a_id=? OR char_b_id=?)""", (char['id'], char['id']), one=True))
    has_pet = bool(char['equipped_pet_id'])
    return xinsui_wish_snapshot(char, mastery_total, dan_idx, has_companion, has_pet)

@app.route('/festival/xinsui/wish', methods=['POST'])
@login_required
def xinsui_wish():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'xinsui' or fest['status'] != 'active':
        flash('当前并无新岁赐福可参与', 'error')
        return redirect(url_for('festival_home'))
    wish_key = request.form.get('wish_key', '')
    if wish_key not in XINSUI_WISHES:
        flash('愿望不存在', 'error')
        return redirect(url_for('festival_home'))
    if q("SELECT 1 FROM xinsui_wishes WHERE festival_id=? AND char_id=?", (fest['id'], char['id']), one=True):
        flash('你本届已经许过愿了', 'error')
        return redirect(url_for('festival_home'))
    new_snapshot = _xinsui_snapshot_inputs(char)
    prior = q("""SELECT * FROM xinsui_wishes WHERE char_id=? AND festival_id!=? ORDER BY created_ts DESC LIMIT 1""",
              (char['id'], fest['id']), one=True)
    review = None
    if prior:
        fulfilled = xinsui_wish_fulfilled(prior['wish_key'], json.loads(prior['snapshot_json']), new_snapshot)
        if fulfilled is not None:
            review = f"去年你许下「{XINSUI_WISHES[prior['wish_key']]['label']}」之愿,如今看来{'已经应验' if fulfilled else '尚未应验'}。"
    try:
        run("""INSERT INTO xinsui_wishes (festival_id,char_id,wish_key,snapshot_json,created_ts)
               VALUES (?,?,?,?,?)""", (fest['id'], char['id'], wish_key, json.dumps(new_snapshot), now_ts()))
    except sqlite3.IntegrityError:
        flash('你本届已经许过愿了', 'error')
        return redirect(url_for('festival_home'))
    msg = f"已许下「{XINSUI_WISHES[wish_key]['label']}」之愿,静候新岁降福。"
    flash(f"{msg}{review}" if review else msg, 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/xinsui/activity', methods=['POST'])
@login_required
def xinsui_activity():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'xinsui' or fest['status'] != 'active':
        flash('当前并无新岁赐福可参与', 'error')
        return redirect(url_for('festival_home'))
    activity_key = request.form.get('activity_key', '')
    if activity_key not in XINSUI_ACTIVITIES:
        flash('除岁活动不存在', 'error')
        return redirect(url_for('festival_home'))
    if q("SELECT 1 FROM xinsui_activity WHERE festival_id=? AND char_id=?", (fest['id'], char['id']), one=True):
        flash('你本届已经参与过除岁活动了', 'error')
        return redirect(url_for('festival_home'))
    name_label = f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
    line = xinsui_activity_line(activity_key, _weapon_style(char), name_label)
    try:
        run("""INSERT INTO xinsui_activity (festival_id,char_id,activity_key,line_text,created_ts)
               VALUES (?,?,?,?,?)""", (fest['id'], char['id'], activity_key, line, now_ts()))
    except sqlite3.IntegrityError:
        flash('你本届已经参与过除岁活动了', 'error')
        return redirect(url_for('festival_home'))
    count = q("SELECT COUNT(*) c FROM xinsui_activity WHERE festival_id=?", (fest['id'],), one=True)['c']
    new_stage = xinsui_stage_index(count)
    old_stage = xinsui_stage_index(count - 1)
    if new_stage > old_stage:
        stage = XINSUI_STAGES[new_stage]
        log_chronicle(f"新岁赐福·{stage['label']}:{stage['text']}", major=True)
    flash(f"已完成「{XINSUI_ACTIVITIES[activity_key]['label']}」这项除岁活动", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/xinsui/blessing/send', methods=['POST'])
@login_required
def xinsui_blessing_send():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    fest = _festival_latest()
    if fest:
        fest = dict(_festival_resolve_expiry(fest))
    if not fest or fest['type_key'] != 'xinsui' or fest['status'] != 'active':
        flash('当前并无新岁赐福可参与', 'error')
        return redirect(url_for('festival_home'))
    to_char_id = request.form.get('to_char_id', type=int)
    message = request.form.get('message', '').strip()[:200]
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0 AND is_npc=0",
               (to_char_id,), one=True) if to_char_id else None
    if not target or target['id'] == char['id']:
        flash('赠送对象不存在', 'error')
        return redirect(url_for('festival_home'))
    if not message:
        message = random.choice(XINSUI_WISH_BLESSINGS[random.choice(list(XINSUI_WISHES))])
    gift = xinsui_blessing_roll()
    run("""INSERT INTO xinsui_blessings (festival_id,from_char_id,to_char_id,gift_name,rarity_key,message,
           opened,created_ts) VALUES (?,?,?,?,?,?,0,?)""",
        (fest['id'], char['id'], target['id'], gift['name'], gift['rarity_key'], message, now_ts()))
    send_system_mail(target['id'], '一份福签', f"{char['name']}给你寄来一枚{gift['name']},请到「宗门节日」页查收。")
    flash(f"已将{gift['name']}寄给{target['name']}", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/festival/xinsui/blessing/<int:blessing_id>/open', methods=['POST'])
@login_required
def xinsui_blessing_open(blessing_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    b = q("SELECT * FROM xinsui_blessings WHERE id=? AND to_char_id=? AND opened=0",
          (blessing_id, char['id']), one=True)
    if not b:
        flash('这份福签不存在或已拆开', 'error')
        return redirect(url_for('festival_home'))
    run("UPDATE xinsui_blessings SET opened=1, opened_ts=? WHERE id=?", (now_ts(), blessing_id))
    apply_reward(char['id'], XINSUI_BLESSING_REWARD)
    flash(f"拆开了{b['gift_name']},里面写着:{b['message']}", 'ok')
    return redirect(url_for('festival_home'))

@app.route('/admin/festival', methods=['GET', 'POST'])
@admin_required
def admin_festival():
    last = _festival_latest()
    can_open = (not last) or last['status'] != 'active'
    if request.method == 'POST':
        if not can_open:
            flash('当前仍有节日活动进行中', 'error')
            return redirect(url_for('admin_festival'))
        type_key = request.form.get('type_key')
        if type_key not in FESTIVAL_TYPES:
            flash('未知节日类型', 'error')
            return redirect(url_for('admin_festival'))
        run("INSERT INTO festivals (type_key,status,opened_ts,ends_ts) VALUES (?,'active',?,?)",
            (type_key, now_ts(), now_ts() + FESTIVAL_DURATION_HOURS * 3600))
        label = FESTIVAL_TYPES[type_key]['label']
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], label,
                              f"{label}将于{FESTIVAL_DURATION_HOURS}小时后落幕,届时公布盛况。",
                              from_label='宗门公告')
        log_chronicle(f"{label}开启", major=True)
        log_admin('open_festival', 'festival', None, type_key)
        flash(f'{label}已开启', 'ok')
        return redirect(url_for('admin_festival'))
    return render_template('admin/festival.html', last=last, can_open=can_open, now_ts=now_ts(),
                            FESTIVAL_TYPES=FESTIVAL_TYPES, FESTIVAL_TYPES_IMPLEMENTED=FESTIVAL_TYPES_IMPLEMENTED,
                            FESTIVAL_DURATION_HOURS=FESTIVAL_DURATION_HOURS)

@app.route('/admin/festival/close', methods=['POST'])
@admin_required
def admin_festival_close():
    fest = _festival_latest()
    if fest and fest['status'] == 'active':
        run("UPDATE festivals SET ends_ts=? WHERE id=?", (now_ts() - 1, fest['id']))
        _festival_resolve_expiry(dict(q("SELECT * FROM festivals WHERE id=?", (fest['id'],), one=True)))
        log_admin('close_festival', 'festival', fest['id'], fest['type_key'])
        flash('已手动收尾当前节日活动', 'ok')
    else:
        flash('当前没有进行中的节日活动', 'error')
    return redirect(url_for('admin_festival'))

# ── 闭关:懒惰结算的挂机选项,期间锁定打坐/委托/探索,出关后一次性结算修为+贡献 ─────────

def _retreat_hourly_exp(char):
    root_mult = SPIRIT_ROOTS.get(char['spirit_root'], {}).get('mult', 1.0)
    realm_mult = BASE_EXP_REALM_MULT.get(realm_major_idx(char['realm_idx']), 1)
    qi_bonus = 1 + cave_band_pct(cave_qi(char)) / 100
    return round(RETREAT_EXP_BASE_PER_HOUR * root_mult * realm_mult * qi_bonus)

def _retreat_diminish_units(char, gained_exp):
    """闭关按实际收益折算成"相当于打坐几次"计入每日衰减额度,而非按小时数走固定倍率——
    收益越接近打坐的产出,占用的每日额度就越接近打坐本身,不会因为挂机时长长就显得更"便宜"。"""
    root_mult = SPIRIT_ROOTS.get(char['spirit_root'], {}).get('mult', 1.0)
    realm_mult = BASE_EXP_REALM_MULT.get(realm_major_idx(char['realm_idx']), 1)
    avg_method_mult = sum(m['exp_mult'] for m in CULTIVATE_METHODS.values()) / len(CULTIVATE_METHODS)
    avg_click_exp = CULTIVATE_BASE_EXP_AVG * root_mult * realm_mult * avg_method_mult  # 不叠加心境等百分比加成,与闭关自身口径一致
    return max(1, round(gained_exp / avg_click_exp)) if avg_click_exp > 0 else 1

def _tiered_reward(full_amount, full_units, done_before, soft_cap, hard_cap_extra, diminish_mult):
    """把一次性大额收益(闭关/打工)按今日已用额度切成三段:额度内全额、超额但未到硬顶部分打折、
    过了硬顶的部分直接不给——避免"只要愿意打折就能无限刷"的漏洞,硬顶之外当天彻底没有产出。"""
    if full_units <= 0:
        return 0
    hard_cap = soft_cap + hard_cap_extra
    remaining_full = max(0, soft_cap - done_before)
    remaining_diminished = max(0, hard_cap - max(done_before, soft_cap))
    full_band = min(full_units, remaining_full)
    diminished_band = min(max(0, full_units - full_band), remaining_diminished)
    frac_full = full_band / full_units
    frac_dim = diminished_band / full_units
    return full_amount * frac_full + full_amount * diminish_mult * frac_dim

@app.route('/retreat')
@login_required
def retreat_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    active = bool(char['retreat_started_ts'])  # 有会话就显示出关入口,不能只看"是否还在倒计时"——
    ready = active and now_ts() >= char['retreat_until_ts']  # 时辰一到,人不点也不会自动消失
    return render_template('retreat.html', char=char, active=active, ready=ready,
                            remaining=max(0, char['retreat_until_ts'] - now_ts()) if active else 0,
                            durations=RETREAT_DURATION_HOURS, hourly_exp=_retreat_hourly_exp(char),
                            hourly_contribution=RETREAT_CONTRIBUTION_PER_HOUR)

@app.route('/retreat/start', methods=['POST'])
@login_required
def retreat_start():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['retreat_started_ts']:
        flash('上一次闭关还没出关结算,先去领取再开始新的', 'error')
        return redirect(url_for('retreat_home'))
    if char['labor_started_ts']:
        flash('还有一份差事没收工结算,先去领取再开始新的', 'error')
        return redirect(url_for('labor_home'))
    try:
        hours = int(request.form.get('hours', 0))
    except ValueError:
        hours = 0
    if hours not in RETREAT_DURATION_HOURS:
        flash('时长不合法', 'error')
        return redirect(url_for('retreat_home'))
    ts = now_ts()
    run("UPDATE characters SET retreat_started_ts=?, retreat_until_ts=?, retreat_notify_sent=0 WHERE id=?",
        (ts, ts + hours * 3600, char['id']))
    flash(f"已闭关静修,预计{hours}小时后可出关", 'ok')
    return redirect(url_for('retreat_home'))

@app.route('/retreat/claim', methods=['POST'])
@login_required
def retreat_claim():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['retreat_started_ts']:
        flash('尚未闭关', 'error')
        return redirect(url_for('retreat_home'))
    ts = now_ts()
    full = ts >= char['retreat_until_ts']
    elapsed_hours = (min(ts, char['retreat_until_ts']) - char['retreat_started_ts']) / 3600
    mult = 1.0 if full else RETREAT_EARLY_EXIT_MULT
    full_exp = round(_retreat_hourly_exp(char) * elapsed_hours * mult)
    full_contribution = round(RETREAT_CONTRIBUTION_PER_HOUR * elapsed_hours * mult)
    done_today = get_daily_counter(char['id'], 'cultivate_diminish')
    full_units = _retreat_diminish_units(char, full_exp)
    remaining_budget = max(0, CULTIVATE_DIMINISH_AFTER - done_today)
    # 分三段结算:额度内全额、超额但没到硬顶的部分打折、过了硬顶的部分直接不给——
    # 比如只剩1点额度却开了个会耗40点的大闭关,不能靠"反正打折"就无限刷,硬顶之外当天彻底没有产出。
    diminished = full_units > remaining_budget
    gained_exp = round(_tiered_reward(full_exp, full_units, done_today,
                                       CULTIVATE_DIMINISH_AFTER, CULTIVATE_DIMINISH_HARD_CAP_EXTRA, CULTIVATE_DIMINISH_MULT))
    gained_contribution = round(_tiered_reward(full_contribution, full_units, done_today,
                                       CULTIVATE_DIMINISH_AFTER, CULTIVATE_DIMINISH_HARD_CAP_EXTRA, CULTIVATE_DIMINISH_MULT))
    retreat_capped = False
    if char['realm_idx'] < MAX_REALM_INDEX:
        room = REALMS[char['realm_idx'] + 1]['exp'] - char['exp']
        if gained_exp >= room:
            gained_exp = max(0, room)
            retreat_capped = True
    run("UPDATE characters SET exp=exp+?, contribution=contribution+?, total_contribution=total_contribution+?, "
        "technique_deviation=MAX(0,technique_deviation-10), retreat_started_ts=0, retreat_until_ts=0 WHERE id=?",
        (gained_exp, gained_contribution, gained_contribution, char['id']))
    bump_daily_counter(char['id'], 'cultivate_diminish', amount=full_units)
    mark_daily_task(char['id'], 'cultivate')
    check_achievements(char['id'])
    tag = '(圆满出关)' if full else '(提前出关,收益减半)'
    msg = f"出关{tag}:修为 +{gained_exp}、贡献 +{gained_contribution}"
    if done_today >= CULTIVATE_DIMINISH_AFTER + CULTIVATE_DIMINISH_HARD_CAP_EXTRA:
        msg += '(今日打坐/闭关已严重超量,不再有产出)'
    elif diminished:
        msg += '(今日打坐/闭关已过量,超出部分收益打折,快到硬顶了)'
    if retreat_capped:
        msg += ',修为已抵瓶颈,需先突破方可再进'
    flash(msg, 'ok')
    return redirect(url_for('home'))

# ── 灵石:独立于贡献的第二货币,双向可兑但不对等(功勋换钱好换,钱买不到功勋) ────────────

@app.route('/lingshi/exchange', methods=['POST'])
@login_required
def lingshi_exchange():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    direction = request.form.get('direction')
    try:
        amount = int(request.form.get('amount', 0))
    except ValueError:
        amount = 0
    if amount <= 0:
        flash('数量不合法', 'error')
        return redirect(url_for('cave_home'))
    if direction == 'to_lingshi':
        gained = amount // CONTRIBUTION_TO_LINGSHI_RATE
        spent = gained * CONTRIBUTION_TO_LINGSHI_RATE
        if gained <= 0:
            flash(f'至少需要{CONTRIBUTION_TO_LINGSHI_RATE}贡献才能兑换1灵石', 'error')
            return redirect(url_for('cave_home'))
        cur = run("UPDATE characters SET contribution=contribution-?, lingshi=lingshi+? WHERE id=? AND contribution>=?",
                  (spent, gained, char['id'], spent))
        if cur.rowcount == 0:
            flash('贡献不足', 'error')
            return redirect(url_for('cave_home'))
        flash(f"以{spent}贡献兑得{gained}灵石", 'ok')
    elif direction == 'to_contribution':
        if get_daily_counter(char['id'], 'lingshi_exchange') >= LINGSHI_EXCHANGE_DAILY_LIMIT:
            flash('今日兑换次数已用完', 'error')
            return redirect(url_for('cave_home'))
        gained = amount // LINGSHI_TO_CONTRIBUTION_RATE
        spent = gained * LINGSHI_TO_CONTRIBUTION_RATE
        if gained <= 0:
            flash(f'至少需要{LINGSHI_TO_CONTRIBUTION_RATE}灵石才能兑换1贡献', 'error')
            return redirect(url_for('cave_home'))
        # 只加可用贡献,不计入 total_contribution——钱买不到晋升所需的宗门功勋
        cur = run("UPDATE characters SET lingshi=lingshi-?, contribution=contribution+? WHERE id=? AND lingshi>=?",
                  (spent, gained, char['id'], spent))
        if cur.rowcount == 0:
            flash('灵石不足', 'error')
            return redirect(url_for('cave_home'))
        bump_daily_counter(char['id'], 'lingshi_exchange')
        flash(f"以{spent}灵石兑得{gained}贡献", 'ok')
    else:
        flash('未知兑换方向', 'error')
    return redirect(url_for('cave_home'))

# ── 洞府 ───────────────────────────────────────────────────────────────────────

@app.route('/cave')
@login_required
def cave_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    char = sync_cave_array(char)
    if not char['cave_scenery']:
        scenery = roll_cave_scenery()
        run("UPDATE characters SET cave_scenery=? WHERE id=?", (scenery, char['id']))
        char['cave_scenery'] = scenery
    if not char['cave_name']:
        char['cave_name'] = roll_cave_name(char['cave_scenery'])
        run("UPDATE characters SET cave_name=? WHERE id=?", (char['cave_name'], char['id']))
    tier = cave_tier_info(char['cave_tier'])
    next_tier = CAVE_TIERS[char['cave_tier'] + 1] if char['cave_tier'] < CAVE_MAX_TIER_INDEX else None
    materials = {r['material_key']: r['qty'] for r in q(
        "SELECT material_key, qty FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))}
    owned_decorations = {r['decoration_key'] for r in q(
        "SELECT decoration_key FROM character_decorations WHERE char_id=?", (char['id'],))}
    traits = cave_traits_list(char)
    array = cave_array_info(char['cave_array_level'])
    next_array = CAVE_ARRAY_LEVELS[char['cave_array_level']] if char['cave_array_level'] < CAVE_ARRAY_MAX_LEVEL else None
    garden_ready = bool(char['cave_garden_seed']) and now_ts() >= char['cave_garden_ready_ts']
    garden_crop = CAVE_GARDEN_CROPS_BY_KEY.get(char['cave_garden_seed']) if char['cave_garden_seed'] else None
    qi, purity, stability = cave_qi(char), cave_purity(char), cave_stability(char)
    return render_template('cave.html', char=char, tier=tier, next_tier=next_tier, realm_by_index=realm_by_index,
                            materials=materials, material_labels=MATERIAL_LABELS, MATERIAL_TIERS=MATERIAL_TIERS,
                            owned_decorations=owned_decorations, traits=traits, cave_traits_data=CAVE_TRAITS,
                            array=array, next_array=next_array,
                            garden_ready=garden_ready, garden_crop=garden_crop, crops=CAVE_GARDEN_CROPS,
                            cave_qi=qi, cave_purity=purity, cave_stability=stability,
                            qi_bonus_pct=cave_band_pct(qi), purity_reduction_pct=cave_band_pct(purity),
                            stability_discount=cave_stability_stamina_discount(stability),
                            contrib_rate=CONTRIBUTION_TO_LINGSHI_RATE, lingshi_rate=LINGSHI_TO_CONTRIBUTION_RATE,
                            exchange_limit=LINGSHI_EXCHANGE_DAILY_LIMIT,
                            exchanges_today=get_daily_counter(char['id'], 'lingshi_exchange'))

@app.route('/cave/rename', methods=['POST'])
@login_required
def cave_rename():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    name = request.form.get('name', '').strip()[:16]
    run("UPDATE characters SET cave_name=? WHERE id=?", (name or None, char['id']))
    flash(f"洞府更名为「{name}」" if name else '已清空洞府之名', 'ok')
    return redirect(url_for('cave_home'))

@app.route('/cave/upgrade', methods=['POST'])
@login_required
def cave_upgrade():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['cave_tier'] >= CAVE_MAX_TIER_INDEX:
        flash('洞府已至洞天福地,道途尽头', 'error')
        return redirect(url_for('cave_home'))
    next_tier = CAVE_TIERS[char['cave_tier'] + 1]
    if char['realm_idx'] < next_tier['realm_req']:
        flash(f"修为不足,需达到 {REALMS[next_tier['realm_req']]['name']}", 'error')
        return redirect(url_for('cave_home'))
    if next_tier['rank_req'] and char['rank_tier'] < next_tier['rank_req']:
        flash('身份不足,无法扩建至此品阶', 'error')
        return redirect(url_for('cave_home'))
    if not _has_materials(char['id'], next_tier['materials']):
        flash('灵材不足', 'error')
        return redirect(url_for('cave_home'))
    cur = run("UPDATE characters SET lingshi=lingshi-?, cave_tier=cave_tier+1 WHERE id=? AND lingshi>=? AND cave_tier=?",
              (next_tier['lingshi_cost'], char['id'], next_tier['lingshi_cost'], char['cave_tier']))
    if cur.rowcount == 0:
        flash('灵石不足', 'error')
        return redirect(url_for('cave_home'))
    _consume_materials(char['id'], next_tier['materials'])
    msg = f"洞府扩建为{next_tier['label']}!"
    traits = cave_traits_list(char)
    new_trait = roll_cave_trait(traits)
    if new_trait:
        traits.append(new_trait)
        run("UPDATE characters SET cave_traits=? WHERE id=?", (json.dumps(traits), char['id']))
        msg += f" 洞府中忽然显现异象——{CAVE_TRAITS[new_trait]['label']}!"
    check_achievements(char['id'])
    flash(msg, 'ok')
    return redirect(url_for('cave_home'))

@app.route('/cave/array/build', methods=['POST'])
@login_required
def cave_array_build():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_cave_array(char)
    if char['cave_array_level'] >= CAVE_ARRAY_MAX_LEVEL:
        flash('聚灵阵已至最高等级', 'error')
        return redirect(url_for('cave_home'))
    next_level = CAVE_ARRAY_LEVELS[char['cave_array_level']]
    if next_level.get('min_cave_tier') and char['cave_tier'] < next_level['min_cave_tier']:
        flash('洞府品阶不足,无法建造此阵法', 'error')
        return redirect(url_for('cave_home'))
    if not _has_materials(char['id'], next_level['materials']):
        flash('灵材不足', 'error')
        return redirect(url_for('cave_home'))
    cur = run("""UPDATE characters SET lingshi=lingshi-?, cave_array_level=cave_array_level+1, cave_array_ts=?
                 WHERE id=? AND lingshi>=? AND cave_array_level=?""",
              (next_level['lingshi_cost'], now_ts(), char['id'], next_level['lingshi_cost'], char['cave_array_level']))
    if cur.rowcount == 0:
        flash('灵石不足', 'error')
        return redirect(url_for('cave_home'))
    _consume_materials(char['id'], next_level['materials'])
    flash(f"聚灵阵升级为{next_level['label']}!", 'ok')
    return redirect(url_for('cave_home'))

@app.route('/cave/garden/plant/<crop_key>', methods=['POST'])
@login_required
def cave_garden_plant(crop_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['cave_garden_seed']:
        flash('药圃里已有作物在生长', 'error')
        return redirect(url_for('cave_home'))
    crop = CAVE_GARDEN_CROPS_BY_KEY.get(crop_key)
    if not crop:
        flash('未知作物', 'error')
        return redirect(url_for('cave_home'))
    if char['cave_tier'] < crop['min_cave_tier']:
        flash('洞府品阶不足,种不了这个', 'error')
        return redirect(url_for('cave_home'))
    run("UPDATE characters SET cave_garden_seed=?, cave_garden_ready_ts=? WHERE id=?",
        (crop_key, now_ts() + crop['hours'] * 3600, char['id']))
    flash(f"种下{crop['label']},{crop['hours']}小时后可收获", 'ok')
    return redirect(url_for('cave_home'))

@app.route('/cave/garden/harvest', methods=['POST'])
@login_required
def cave_garden_harvest():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['cave_garden_seed']:
        flash('药圃里没有作物', 'error')
        return redirect(url_for('cave_home'))
    if now_ts() < char['cave_garden_ready_ts']:
        flash('作物尚未成熟', 'error')
        return redirect(url_for('cave_home'))
    crop = CAVE_GARDEN_CROPS_BY_KEY[char['cave_garden_seed']]
    gained_lingshi = random.randint(*crop['lingshi_range'])
    run("UPDATE characters SET lingshi=lingshi+?, cave_garden_seed=NULL, cave_garden_ready_ts=0 WHERE id=?",
        (gained_lingshi, char['id']))
    drops = []
    for material_key, chance in crop['material_drop'].items():
        if random.random() < chance:
            _grant_material(char['id'], material_key, 1)
            drops.append(MATERIAL_LABELS[material_key])
    msg = f"收获{crop['label']},得灵石 {gained_lingshi}"
    if drops:
        msg += '、' + '、'.join(drops)
    flash(msg, 'ok')
    return redirect(url_for('cave_home'))

@app.route('/cave/decoration/build/<trait_key>', methods=['POST'])
@login_required
def cave_decoration_build(trait_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    trait = CAVE_TRAITS.get(trait_key)
    if not trait or trait_key not in cave_traits_list(char):
        flash('尚未拥有这个洞府特征', 'error')
        return redirect(url_for('cave_home'))
    if q("SELECT 1 FROM character_decorations WHERE char_id=? AND decoration_key=?",
         (char['id'], trait['decoration_key']), one=True):
        flash('已经建过这个装饰了', 'error')
        return redirect(url_for('cave_home'))
    if char['lingshi'] < trait['lingshi_cost']:
        flash('灵石不足', 'error')
        return redirect(url_for('cave_home'))
    if not _has_materials(char['id'], trait['materials']):
        flash('灵材不足', 'error')
        return redirect(url_for('cave_home'))
    if not _spend(char['id'], 'lingshi', trait['lingshi_cost']):
        flash('灵石不足', 'error')
        return redirect(url_for('cave_home'))
    _consume_materials(char['id'], trait['materials'])
    run("INSERT INTO character_decorations (char_id,decoration_key,built_ts) VALUES (?,?,?)",
        (char['id'], trait['decoration_key'], now_ts()))
    flash(f"建成{trait['decoration_label']}", 'ok')
    return redirect(url_for('cave_home'))

# ── 洞府地图:入门先住宗门公共居所,拜师入峰后解锁本峰弟子居所,可搬迁(单向,峰本就终身唯一) ──

@app.route('/cave/map')
@login_required
def cave_map():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    peak_name = _peak_name(char)
    locations = [{'name': name, 'bonus': bonus, 'unlocked': name == peak_name,
                  'current': char['cave_location'] == name}
                 for name, bonus in CAVE_PEAK_BONUS.items()]
    return render_template('cave_map.html', char=char, locations=locations, peak_name=peak_name,
                            at_common=(not char['cave_location'] or char['cave_location'] == CAVE_LOCATION_COMMON))

@app.route('/cave/relocate', methods=['POST'])
@login_required
def cave_relocate():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    peak_name = _peak_name(char)
    if not peak_name:
        flash('尚未拜师入峰,还没有资格搬进师门居所', 'error')
        return redirect(url_for('cave_map'))
    if char['cave_location'] == peak_name:
        flash('你已经住在此处', 'error')
        return redirect(url_for('cave_map'))
    run("UPDATE characters SET cave_location=? WHERE id=?", (peak_name, char['id']))
    log_chronicle(f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
                   f"搬入{peak_name}弟子居所,与师兄弟比邻而居")
    flash(f"已搬入{peak_name}弟子居所", 'ok')
    return redirect(url_for('cave_map'))

# ── 档位晋升 ───────────────────────────────────────────────────────────────────

@app.route('/promote')
@login_required
def promote():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    rank = rank_by_tier(char['rank_tier'])
    next_rank = rank_by_tier(char['rank_tier'] + 1) if char['rank_tier'] < MAX_EXAM_TIER else None
    peak_elder_status = None
    if next_rank and next_rank['tier'] == 5:
        if not char['peak_id']:
            peak_elder_status = 'no_peak'
        else:
            target_peak = q("SELECT * FROM peaks WHERE id=?", (char['peak_id'],), one=True)
            if target_peak['is_leader']:
                peak_elder_status = 'leader_peak'
            elif not target_peak['elder_id']:
                peak_elder_status = 'vacant'
            else:
                incumbent = q("SELECT is_npc FROM characters WHERE id=?", (target_peak['elder_id'],), one=True)
                peak_elder_status = 'npc' if incumbent and incumbent['is_npc'] else 'player'
    exams_today = get_daily_counter(char['id'], 'promotion_exam')
    return render_template('promote.html', char=char, rank=rank, next_rank=next_rank,
                            peak_elder_status=peak_elder_status, exams_today=exams_today,
                            exam_limit=PROMOTION_EXAM_DAILY_LIMIT, realm_by_index=realm_by_index)

@app.route('/promote/exam', methods=['POST'])
@login_required
def promote_exam():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['rank_tier'] >= MAX_EXAM_TIER:
        flash('已是长老,掌门之位唯有继任产生', 'error')
        return redirect(url_for('promote'))

    next_rank = rank_by_tier(char['rank_tier'] + 1)
    target_peak = None
    npc_incumbent = None
    if next_rank['tier'] == 5:
        if not char['peak_id']:
            flash('需先拜入一峰,方可参选本峰长老之位', 'error')
            return redirect(url_for('promote'))
        target_peak = q("SELECT * FROM peaks WHERE id=?", (char['peak_id'],), one=True)
        if target_peak['is_leader']:
            flash('掌门峰弟子无法通过考核成为长老,唯有静候明主垂青', 'error')
            return redirect(url_for('promote'))
        if target_peak['elder_id']:
            incumbent = q("SELECT * FROM characters WHERE id=?", (target_peak['elder_id'],), one=True)
            if incumbent and incumbent['is_npc']:
                npc_incumbent = incumbent
            else:
                flash(f"{target_peak['name']}长老之位已有人在任,暂无空缺", 'error')
                return redirect(url_for('promote'))

    if char['realm_idx'] < next_rank['realm_req']:
        flash(f"修为不足,需达到 {REALMS[next_rank['realm_req']]['name']}", 'error')
        return redirect(url_for('promote'))
    if char['total_contribution'] < next_rank['contribution_req']:
        flash(f"贡献不足,需累计贡献达到 {next_rank['contribution_req']}", 'error')
        return redirect(url_for('promote'))
    if char['reputation'] < next_rank['reputation_req']:
        flash(f"声望不足,需宗门声望达到 {next_rank['reputation_req']}", 'error')
        return redirect(url_for('promote'))
    if get_daily_counter(char['id'], 'promotion_exam') >= PROMOTION_EXAM_DAILY_LIMIT:
        flash('今日考核次数已用完,明日再来', 'error')
        return redirect(url_for('promote'))

    bump_daily_counter(char['id'], 'promotion_exam')
    if random.random() <= next_rank['exam_success_rate']:
        run("UPDATE characters SET rank_tier=? WHERE id=?", (next_rank['tier'], char['id']))
        if target_peak:
            if npc_incumbent:
                retire_character(npc_incumbent['id'], 'ascended',
                                  label=f"见{char['name']}崭露头角、技惊四座,自愿让贤,飘然隐退")
            run("UPDATE peaks SET elder_id=? WHERE id=?", (char['id'], target_peak['id']))
            title = title_for(char['join_seq'], char['gender'])
            verb = '力压NPC长老,考核夺得' if npc_incumbent else '考核通过,执掌'
            log_chronicle(f"{char['name']}({title}){verb}{target_peak['name']}长老之位", major=True)
        check_achievements(char['id'])
        flash(f"考核通过!晋升为{next_rank['label']}", 'ok')
    else:
        flash('考核未过,再接再厉', 'error')
    return redirect(url_for('promote'))

# ── 休整 / 请教同门:每日限次,不消耗体力,靠 daily_counters 防刷 ───────────────────

REST_DAILY_LIMIT = 3
INTERACT_DAILY_LIMIT = 3

@app.route('/rest', methods=['POST'])
@login_required
def rest():
    char = me_character()
    if not char:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='角色不存在'), 404
        return redirect(url_for('create_character'))
    if get_daily_counter(char['id'], 'rest') >= REST_DAILY_LIMIT:
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, message='今日已休整多次，该出去走走了'), 429
        flash('今日已休整多次,该出去走走了', 'error')
        return redirect(url_for('home'))
    bump_daily_counter(char['id'], 'rest')
    apply_reward(char['id'], {'stamina': 18, 'mind_state': 3})
    mark_daily_task(char['id'], 'rest')
    if request.accept_mimetypes.best == 'application/json':
        updated = q("SELECT stamina,mind_state FROM characters WHERE id=?", (char['id'],), one=True)
        return jsonify(ok=True, kind='rest', message='稍作休整，体力与心境都恢复了一些', rare=False,
                       gained={'stamina': updated['stamina'] - char['stamina'],
                               'mind': updated['mind_state'] - char['mind_state']},
                       stats={'stamina': updated['stamina'], 'mind': updated['mind_state']})
    flash('稍作休整,体力与心境都恢复了一些', 'ok')
    return redirect(url_for('home'))

@app.route('/interact/<int:char_id>', methods=['POST'])
@login_required
def interact(char_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char_id == char['id']:
        flash('不能向自己请教', 'error')
        return redirect(url_for('roster'))
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0", (char_id,), one=True)
    if not target:
        flash('对方不在宗门中', 'error')
        return redirect(url_for('roster'))
    if get_daily_counter(char['id'], 'interact') >= INTERACT_DAILY_LIMIT:
        flash('今日已请教多次同门', 'error')
        return redirect(url_for('roster'))
    bump_daily_counter(char['id'], 'interact')
    apply_reward(char['id'], {'reputation': 3})
    apply_reward(target['id'], {'reputation': 1})
    mark_daily_task(char['id'], 'interact')
    flash(f"向{target['name']}请教一番,声望+3", 'ok')
    return redirect(url_for('roster'))

# ── 宗门委托:消耗体力换贡献/声望/体魄,每日前3次全额,之后减半 ─────────────────────

@app.route('/commissions')
@login_required
def commissions_list():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    done_today = get_daily_counter(char['id'], 'commission')
    diminished = done_today >= COMMISSION_DIMINISH_AFTER
    commissions = [dict(c, reward_desc=_reward_desc(c['reward']),
                         stamina_cost=c['stamina_cost'] * (COMMISSION_DIMINISH_STAMINA_MULT if diminished else 1))
                   for c in COMMISSIONS]
    return render_template('commissions.html', char=char, commissions=commissions, done_today=done_today,
                            diminish_after=COMMISSION_DIMINISH_AFTER, diminished=diminished)

@app.route('/commissions/<key>', methods=['POST'])
@login_required
def commission_do(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if in_retreat(char):
        flash('你正在闭关中,心无旁骛,出关后再来', 'error')
        return redirect(url_for('retreat_home'))
    if in_labor(char):
        flash('你正在外出打工,分身乏术,出工后再来', 'error')
        return redirect(url_for('labor_home'))
    char = sync_stamina(char)
    cm = COMMISSIONS_BY_KEY.get(key)
    if not cm:
        flash('委托不存在', 'error')
        return redirect(url_for('commissions_list'))
    done_today = get_daily_counter(char['id'], 'commission')
    diminished = done_today >= COMMISSION_DIMINISH_AFTER
    stamina_cost = cm['stamina_cost'] * (COMMISSION_DIMINISH_STAMINA_MULT if diminished else 1)
    if char['stamina'] < stamina_cost:
        flash('体力不足', 'error')
        return redirect(url_for('commissions_list'))
    mult = COMMISSION_DIMINISH_MULT if diminished else 1.0
    mult *= 1 + get_peak_specialty(char).get('commission_bonus_pct', 0) / 100
    injured = in_severe_injury(char)
    if injured:
        mult *= TRAVEL_MINOR_INJURY_COMMISSION_MULT
    reward = {k: (round(v * mult) if k != 'stamina' else v) for k, v in cm['reward'].items()}
    if 'contribution' in reward:
        reward['contribution'] = round(reward['contribution'] * (1 + dao_bonus(char['id'], 'commission_pct') / 100))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (stamina_cost, char['id']))
    apply_reward(char['id'], reward)
    add_dao_progress(char['id'], 'mercy', daily_cap=3)
    bump_daily_counter(char['id'], 'commission')
    mark_daily_task(char['id'], 'commission')
    check_achievements(char['id'])
    tag = '(身负轻伤,收益减半)' if injured else ('(收益减半,体力消耗翻倍)' if diminished else '')
    flash(f"完成{cm['label']}{tag}", 'ok')
    return redirect(url_for('commissions_list'))

# ── 打工:懒惰结算的挂机选项,专赚灵石(委托赚贡献)——跟闭关同一套模型,期间锁定其他行动 ────

@app.route('/labor')
@login_required
def labor_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    active = bool(char['labor_started_ts'])  # 有会话就显示收工入口,不能只看"是否还在倒计时"
    ready = active and now_ts() >= char['labor_until_ts']  # 时辰一到,人不点也不会自动消失
    job = LABOR_JOBS_BY_KEY.get(char['labor_job_key']) if active else None
    return render_template('labor.html', char=char, active=active, ready=ready, job=job,
                            remaining=max(0, char['labor_until_ts'] - now_ts()) if active else 0,
                            durations=LABOR_DURATION_HOURS, jobs=LABOR_JOBS)

@app.route('/labor/start', methods=['POST'])
@login_required
def labor_start():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['retreat_started_ts']:
        flash('还有一次闭关没出关结算,先去领取再开始新的', 'error')
        return redirect(url_for('retreat_home'))
    if char['labor_started_ts']:
        flash('上一份差事还没收工结算,先去领取再开始新的', 'error')
        return redirect(url_for('labor_home'))
    job = LABOR_JOBS_BY_KEY.get(request.form.get('job_key'))
    try:
        hours = int(request.form.get('hours', 0))
    except ValueError:
        hours = 0
    if not job or hours not in LABOR_DURATION_HOURS:
        flash('差事或时长不合法', 'error')
        return redirect(url_for('labor_home'))
    ts = now_ts()
    run("UPDATE characters SET labor_job_key=?, labor_started_ts=?, labor_until_ts=?, labor_notify_sent=0 WHERE id=?",
        (job['key'], ts, ts + hours * 3600, char['id']))
    flash(f"已外出{job['label']},预计{hours}小时后可收工", 'ok')
    return redirect(url_for('labor_home'))

@app.route('/labor/claim', methods=['POST'])
@login_required
def labor_claim():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['labor_started_ts']:
        flash('尚未外出打工', 'error')
        return redirect(url_for('labor_home'))
    job = LABOR_JOBS_BY_KEY.get(char['labor_job_key']) or LABOR_JOBS[0]
    ts = now_ts()
    full = ts >= char['labor_until_ts']
    elapsed_hours = (min(ts, char['labor_until_ts']) - char['labor_started_ts']) / 3600
    done_hours_today = get_daily_counter(char['id'], 'labor_diminish')
    full_lingshi = job['lingshi_per_hour'] * elapsed_hours
    # 分三段结算:额度内全价、超时但没到硬顶的部分打折、过了硬顶的部分直接不给——
    # 提前收工按实际做工时长照单全付,只是这部分时长本身仍然要走衰减判定,不是绕开衰减的手段。
    diminished = elapsed_hours > max(0, LABOR_DIMINISH_AFTER_HOURS - done_hours_today)
    gained_lingshi = round(_tiered_reward(full_lingshi, elapsed_hours, done_hours_today,
                                           LABOR_DIMINISH_AFTER_HOURS, LABOR_DIMINISH_HARD_CAP_EXTRA_HOURS, LABOR_DIMINISH_MULT))
    run("UPDATE characters SET lingshi=lingshi+?, labor_job_key=NULL, labor_started_ts=0, labor_until_ts=0 WHERE id=?",
        (gained_lingshi, char['id']))
    bump_daily_counter(char['id'], 'labor_diminish', amount=max(1, round(elapsed_hours)))
    check_achievements(char['id'])
    tag = '(收工)' if full else '(提前收工)'
    msg = f"{job['label']}{tag}:灵石 +{gained_lingshi}"
    if done_hours_today >= LABOR_DIMINISH_AFTER_HOURS + LABOR_DIMINISH_HARD_CAP_EXTRA_HOURS:
        msg += '(今日打工已严重超量,不再有产出)'
    elif diminished:
        msg += '(今日打工已过量,超出部分收益打折,快到硬顶了)'
    flash(msg, 'ok')
    return redirect(url_for('home'))

# ── 行侠令:独立任务板,随时能点但每日限次,不靠游历/秘境的触发概率 ────────────────────

@app.route('/xiaxia')
@login_required
def xiaxia_list():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    done_today = get_daily_counter(char['id'], 'xiaxia')
    tasks = [t | {'reward_desc': _reward_desc(t['reward']), 'fail_reward_desc': _reward_desc(t.get('fail_reward', {}))}
             for t in XIAXIA_TASKS]
    return render_template('xiaxia.html', char=char, tasks=tasks, done_today=done_today,
                            daily_cap=XIAXIA_DAILY_CAP, my_title=xiaxia_title(char['xiaxia_fame']))

@app.route('/xiaxia/<key>', methods=['POST'])
@login_required
def xiaxia_do(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if in_retreat(char):
        flash('你正在闭关中,心无旁骛,出关后再来', 'error')
        return redirect(url_for('retreat_home'))
    if in_labor(char):
        flash('你正在外出打工,分身乏术,出工后再来', 'error')
        return redirect(url_for('labor_home'))
    char = sync_stamina(char)
    task = XIAXIA_TASKS_BY_KEY.get(key)
    if not task:
        flash('任务不存在', 'error')
        return redirect(url_for('xiaxia_list'))
    if get_daily_counter(char['id'], 'xiaxia') >= XIAXIA_DAILY_CAP:
        flash('今日行侠仗义次数已用完,明日再来', 'error')
        return redirect(url_for('xiaxia_list'))
    if char['stamina'] < task['stamina_cost']:
        flash('体力不足', 'error')
        return redirect(url_for('xiaxia_list'))

    injured = in_severe_injury(char)
    mult = TRAVEL_MINOR_INJURY_COMMISSION_MULT if injured else 1.0
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (task['stamina_cost'], char['id']))
    old_fame = char['xiaxia_fame']

    success = random.random() * 100 <= task['success_rate']
    base_reward = task['reward'] if success else task.get('fail_reward', {})
    reward = {k: round(v * mult) for k, v in base_reward.items()}
    apply_reward(char['id'], reward)
    bump_daily_counter(char['id'], 'xiaxia')
    check_achievements(char['id'])

    dropped_label = None
    if success and random.random() < XIAXIA_EQUIPMENT_DROP_CHANCE:
        item = random.choice(XIAXIA_EQUIPMENT_TEMPLATES)
        run("INSERT INTO character_equipment (char_id,item_key,qty) VALUES (?,?,1) "
            "ON CONFLICT(char_id,item_key) DO UPDATE SET qty=qty+1", (char['id'], item['key']))
        row = q("SELECT lore FROM character_equipment WHERE char_id=? AND item_key=?",
                (char['id'], item['key']), one=True)
        if row and not row['lore']:
            run("UPDATE character_equipment SET lore=? WHERE char_id=? AND item_key=?",
                (roll_equipment_lore('行侠令'), char['id'], item['key']))
        dropped_label = item['label']
    found_gift = _maybe_find_gift(char['id'], 'xiaxia') if success else None

    new_fame = old_fame + reward.get('xiaxia_fame', 0)
    if xiaxia_title(new_fame) != xiaxia_title(old_fame):
        new_title = xiaxia_title(new_fame)
        name_label = f"{char['name']}({title_for(char['join_seq'], char['gender'])})"
        log_chronicle(random_xiaxia_title_up_text(name_label, new_title), major=True)
        send_system_mail(char['id'], '侠名鹊起', f"你的侠名已达「{new_title}」这一档,江湖上渐渐有了你的名号。",
                          from_label='江湖传闻')

    tag = '(身负轻伤,收益减半)' if injured else ''
    msg = f"{'仗义出手,事成' if success else '虽未竟全功,亦有微末之得'}{tag}"
    if dropped_label:
        msg += f",意外拾得「{dropped_label}」"
    if found_gift:
        msg += f"，又得「{found_gift['rarity_label']}·{found_gift['name']}」（{found_gift['trait_label']}），已收入行囊"

    if not char.get('pending_story_key'):
        seen = {r['encounter_key'] for r in q(
            "SELECT encounter_key FROM character_story_encounters WHERE char_id=?", (char['id'],))}
        unseen = [e for e in STORY_ENCOUNTERS if e['key'] not in seen]
        if unseen and random.random() < STORY_ENCOUNTER_TRIGGER_CHANCE:
            picked = random.choice(unseen)
            run("UPDATE characters SET pending_story_key=? WHERE id=?", (picked['key'], char['id']))
            msg += ',途中似乎又撞见了些别的事'

    flash(msg, 'loot' if (success and dropped_label) else ('ok' if success else 'error'))
    return redirect(url_for('xiaxia_list'))

# ── 行侠奇遇:行侠令任务结算后小概率触发的一次性剧情事件,每个角色每条只会遇到一次 ─────────

@app.route('/xiaxia/story')
@login_required
def xiaxia_story():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['pending_story_key']:
        return redirect(url_for('xiaxia_list'))
    encounter = STORY_ENCOUNTERS_BY_KEY.get(char['pending_story_key'])
    if not encounter:
        run("UPDATE characters SET pending_story_key=NULL WHERE id=?", (char['id'],))
        return redirect(url_for('xiaxia_list'))
    return render_template('xiaxia_story.html', char=char, encounter=encounter)

@app.route('/xiaxia/story/<choice_key>', methods=['POST'])
@login_required
def xiaxia_story_resolve(choice_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    encounter = STORY_ENCOUNTERS_BY_KEY.get(char['pending_story_key'])
    if not encounter:
        run("UPDATE characters SET pending_story_key=NULL WHERE id=?", (char['id'],))
        return redirect(url_for('xiaxia_list'))
    choice = next((c for c in encounter['choices'] if c['key'] == choice_key), None)
    if not choice:
        flash('选项不存在', 'error')
        return redirect(url_for('xiaxia_story'))
    apply_reward(char['id'], choice['reward'])
    run("""INSERT INTO character_story_encounters (char_id,encounter_key,choice_key,tag_label,resolved_ts)
           VALUES (?,?,?,?,?) ON CONFLICT(char_id,encounter_key) DO NOTHING""",
        (char['id'], encounter['key'], choice_key, choice['tag'], now_ts()))
    run("UPDATE characters SET pending_story_key=NULL WHERE id=?", (char['id'],))
    add_dao_progress(char['id'], 'freedom', daily_cap=1, counter_suffix='story')
    flash(f"{choice['label']}——{_reward_desc(choice['reward'])},你因此得了「{choice['tag']}」这个说法", 'ok')
    return redirect(url_for('xiaxia_list'))

# ── 秘境:不限时间段,一天最多探索3场(元婴起5场);深入或撤退全靠自己拿捏,不是连点随机按钮 ──
# mystic_sessions.day 借用已有的 TEXT 列编码"日期_当日第几场"(如"2026-08-27_0"),不新增列、
# 不用改表结构;查"今天的场次"一律按日期前缀 LIKE 匹配。

def _mystic_sessions_today_count(char_id):
    """灵珠秘境(合体仪式专属环节)不占用常规秘境的每日场次,自成一条额外线——
    本身已经靠 heti_stage==1 这个闸门卡住入口,不需要再跟其他秘境抢同一个每日上限。"""
    return q("SELECT COUNT(*) c FROM mystic_sessions WHERE char_id=? AND day LIKE ? AND zone_key != 'lingzhu'",
             (char_id, today_str() + '_%'), one=True)['c']

def _mystic_session_today(char_id):
    """优先返回今日仍在进行中的场次;若没有,退而返回今日最近的一场(供查看结算结果)。"""
    return q("""SELECT * FROM mystic_sessions WHERE char_id=? AND day LIKE ?
                ORDER BY (status='active') DESC, id DESC LIMIT 1""",
             (char_id, today_str() + '_%'), one=True)

def _mystic_loot_add(loot_json, reward=None, materials=None, equipment_key=None):
    loot = json.loads(loot_json or '{}')
    if reward:
        bucket = loot.setdefault('reward', {})
        for k, v in reward.items():
            bucket[k] = bucket.get(k, 0) + v
    if materials:
        bucket = loot.setdefault('materials', {})
        for k, v in materials.items():
            bucket[k] = bucket.get(k, 0) + v
    if equipment_key:
        loot.setdefault('equipment', []).append(equipment_key)
    return json.dumps(loot)

def _mystic_loot_credit(char_id, loot_json, factor=1.0):
    loot = json.loads(loot_json or '{}')
    reward = loot.get('reward', {})
    if reward:
        scaled = {k: round(v * factor) for k, v in reward.items() if round(v * factor)}
        if scaled:
            apply_reward(char_id, scaled)
    for mk, qty in loot.get('materials', {}).items():
        qty = round(qty * factor)
        if qty > 0:
            _grant_material(char_id, mk, qty)
    for ek in loot.get('equipment', []):
        if factor >= 1.0 or random.random() < factor:
            _inventory_grant(char_id, 'gear', 1, ek)

def _mystic_env_damage(profile, base, depth):
    dmg = base * MYSTIC_DEPTH_DANGER_MULT.get(depth, 1.0)
    dmg = dmg * (1 - min(0.5, profile['stats']['defense'] / 200))
    return max(1, round(dmg))

def _mystic_faint(char, session):
    _mystic_loot_credit(char['id'], session['sealed_loot_json'], 1.0)
    _mystic_loot_credit(char['id'], session['pending_loot_json'], 1 - MYSTIC_FAINT_LOSS_PCT / 100)
    run("UPDATE mystic_sessions SET status='fainted', hp=0, pending_loot_json='{}', ended_ts=? WHERE id=?",
        (now_ts(), session['id']))
    _apply_injury(char)
    check_achievements(char['id'])
    flash('气血耗尽,你昏迷倒地,被秘境之力排斥而出——未封存的战利品折损过半,伤势持续2小时。', 'error')
    return redirect(url_for('mystic_home'))

def _mystic_finalize(char, session, label='left'):
    _mystic_loot_credit(char['id'], session['sealed_loot_json'], 1.0)
    _mystic_loot_credit(char['id'], session['pending_loot_json'], 1.0)
    run("UPDATE mystic_sessions SET status=?, pending_loot_json='{}', ended_ts=? WHERE id=?",
        (label, now_ts(), session['id']))
    check_achievements(char['id'])
    add_dao_progress(char['id'], 'freedom', daily_cap=1, counter_suffix='mystic')

def _mystic_end(char, session, label='left', msg='你收手离开,今日秘境之行圆满结束,收获已悉数入账。'):
    _mystic_finalize(char, session, label)
    flash(msg, 'ok')
    return redirect(url_for('mystic_home'))

def _mystic_effective_sessions_max(char_id, realm_idx):
    return mystic_daily_sessions_max(realm_idx) + get_daily_counter(char_id, 'mystic_extra_session')

@app.route('/mystic')
@login_required
def mystic_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    session = _mystic_session_today(char['id'])
    zones = [z | {'unlocked': char['realm_idx'] >= z['realm_req']} for z in MYSTIC_ZONES if not z.get('hidden')]
    pending_event = None
    zone = None
    sealed_loot, pending_loot = {}, {}
    if session:
        zone = MYSTIC_ZONES_BY_KEY[session['zone_key']]
        sealed_loot = json.loads(session['sealed_loot_json'] or '{}')
        pending_loot = json.loads(session['pending_loot_json'] or '{}')
        if session['status'] == 'active' and session['pending_event_json']:
            pending_event = json.loads(session['pending_event_json'])
    sessions_today = _mystic_sessions_today_count(char['id'])
    sessions_max = _mystic_effective_sessions_max(char['id'], char['realm_idx'])
    daily_sessions_exhausted = sessions_today >= sessions_max
    return render_template('mystic.html', char=char, zones=zones, myst=session, zone=zone,
                            pending_event=pending_event, sealed_loot=sealed_loot, pending_loot=pending_loot,
                            sealed_loot_reward_desc=_reward_desc(sealed_loot.get('reward', {})),
                            pending_loot_reward_desc=_reward_desc(pending_loot.get('reward', {})),
                            sessions_today=sessions_today, sessions_max=sessions_max,
                            daily_sessions_exhausted=daily_sessions_exhausted,
                            entry_stamina_cost=MYSTIC_ENTRY_STAMINA_COST, stamina_cap=STAMINA_CAP,
                            depth_labels=MYSTIC_DEPTH_LABELS, depth_max=MYSTIC_DEPTH_MAX,
                            heal_uses_max=MYSTIC_HEAL_USES_MAX, realm_by_index=realm_by_index,
                            MATERIAL_LABELS=MATERIAL_LABELS, EQUIPMENT_TEMPLATES_BY_KEY=EQUIPMENT_TEMPLATES_BY_KEY,
                            tiandi_session_cost=TIANDI_MYSTIC_EXTRA_SESSION_COST,
                            tiandi_session_left=max(0, TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP
                                                     - get_daily_counter(char['id'], 'mystic_extra_session')),
                            tiandi_session_cap=TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP)

@app.route('/tiandi/mystic_extra_session', methods=['POST'])
@login_required
def tiandi_mystic_extra_session():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if get_daily_counter(char['id'], 'mystic_extra_session') >= TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP:
        flash(f"今日已用天地精华购买{TIANDI_MYSTIC_EXTRA_SESSION_DAILY_CAP}次额外场次,明日再来", 'error')
        return redirect(url_for('mystic_home'))
    if not _spend(char['id'], 'tiandi_jinghua', TIANDI_MYSTIC_EXTRA_SESSION_COST):
        flash(f"天地精华不足{TIANDI_MYSTIC_EXTRA_SESSION_COST}", 'error')
        return redirect(url_for('mystic_home'))
    bump_daily_counter(char['id'], 'mystic_extra_session')
    flash(f"以天地精华×{TIANDI_MYSTIC_EXTRA_SESSION_COST}购得今日额外1场秘境探索机会", 'ok')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/enter/<zone_key>', methods=['POST'])
@login_required
def mystic_enter(zone_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if in_retreat(char):
        flash('你正在闭关中,心无旁骛,出关后再来', 'error')
        return redirect(url_for('retreat_home'))
    if in_labor(char):
        flash('你正在外出打工,分身乏术,出工后再来', 'error')
        return redirect(url_for('labor_home'))
    if in_severe_injury(char):
        flash('你身负重伤,尚需静养,伤愈后再来', 'error')
        return redirect(url_for('home'))
    zone = MYSTIC_ZONES_BY_KEY.get(zone_key)
    if not zone:
        flash('秘境不存在', 'error')
        return redirect(url_for('mystic_home'))
    if zone_key == 'lingzhu':
        if char['heti_stage'] != 1:
            flash('此境唯有合体渡劫·灵珠秘境这一环节才能踏入', 'error')
            return redirect(url_for('mystic_home'))
        lingzhu_entries = q("SELECT COUNT(*) c FROM mystic_sessions WHERE char_id=? AND zone_key='lingzhu'",
                             (char['id'],), one=True)['c']
        if lingzhu_entries >= HETI_LINGZHU_MAX_ENTRIES:
            flash(f"灵珠秘境一生至多踏入{HETI_LINGZHU_MAX_ENTRIES}次,已用完,灵珠不足只能设法在仅剩场次里拼尽全力", 'error')
            return redirect(url_for('heti_home'))
    if char['realm_idx'] < zone['realm_req']:
        flash(f"修为不足,需达到 {REALMS[zone['realm_req']]['name']} 方可踏入{zone['label']}", 'error')
        return redirect(url_for('mystic_home'))
    existing = _mystic_session_today(char['id'])
    if existing and existing['status'] == 'active':
        flash('尚有一场秘境探索未结束,先了结手头这场', 'error')
        return redirect(url_for('mystic_home'))
    if zone_key != 'lingzhu':
        sessions_today = _mystic_sessions_today_count(char['id'])
        sessions_max = _mystic_effective_sessions_max(char['id'], char['realm_idx'])
        if sessions_today >= sessions_max:
            flash(f"今日已探索{sessions_max}场,明日再来", 'error')
            return redirect(url_for('mystic_home'))
    # 按序号找一个今天还没用过的槽位,不直接信count——旧的两时段方案遗留下来的"_0"/"_1"记录
    # 可能跟新方案的序号撞在一起(比如以前晚上那场恰好是"_1",新方案第2场序号也是"_1"),
    # 直接用count当序号会永远撞车,进不去。
    existing_days = {r['day'] for r in q("SELECT day FROM mystic_sessions WHERE char_id=? AND day LIKE ?",
                                          (char['id'], today_str() + '_%'))}
    slot = 0
    while f"{today_str()}_{slot}" in existing_days:
        slot += 1
    day_key = f"{today_str()}_{slot}"
    char = sync_stamina(char)
    if char['stamina'] < MYSTIC_ENTRY_STAMINA_COST:
        flash('体力不足,无法踏入秘境', 'error')
        return redirect(url_for('mystic_home'))
    profile = _player_combat_profile(char)
    hp_max = profile['stats']['max_hp']
    specialty = get_peak_specialty(char)
    stamina_start = MYSTIC_STAMINA_START + specialty.get('mystic_stamina_bonus', 0)
    charms_start = MYSTIC_ESCAPE_CHARMS_START + specialty.get('mystic_charm_bonus', 0)
    try:
        run("""INSERT INTO mystic_sessions (char_id,day,zone_key,depth,stamina,hp,hp_max,escape_charms,
               heal_uses,hidden_unlocked,sealed_loot_json,pending_loot_json,status,entered_ts)
               VALUES (?,?,?,1,?,?,?,?,0,0,'{}','{}','active',?)""",
            (char['id'], day_key, zone_key, stamina_start, hp_max, hp_max,
             charms_start, now_ts()))
    except sqlite3.IntegrityError:
        # 双击/网络重试导致同一场次重复提交,这一枪已经有人开过了,不重复扣体力
        flash('操作过快,这一场秘境已经进过了,刷新看看当前状态', 'error')
        return redirect(url_for('mystic_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (MYSTIC_ENTRY_STAMINA_COST, char['id']))
    flash(f"踏入{zone['label']},{zone['desc']}", 'ok')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/explore', methods=['POST'])
@login_required
def mystic_explore():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    if session['pending_event_json']:
        flash('先应对眼前之事,再继续前行', 'error')
        return redirect(url_for('mystic_home'))
    if session['stamina'] <= 0:
        flash('探索点数已尽,今日难有更多际遇了', 'error')
        return redirect(url_for('mystic_home'))
    zone = MYSTIC_ZONES_BY_KEY[session['zone_key']]
    depth = session['depth']
    etype = roll_mystic_event_type(depth)
    if etype == 'beast':
        monster_key = random.choice(zone['monster_keys'])
        m = encounter_monster_power(monster_key)
        event = {'type': 'beast', 'monster_key': monster_key,
                 'text': f"一只{m['label']}忽然现身,挡住了去路。"}
    elif etype == 'herb':
        event = {'type': 'herb', 'text': '你发现一株尚未成熟的灵药——现在采摘只能得几分药性,若等它成熟,收获更丰,但也可能被人捷足先登。'}
    elif etype == 'satchel':
        event = {'type': 'satchel', 'text': '草丛中露出半只储物袋,像是哪位修士遗落于此。'}
    elif etype == 'cultivator':
        event = {'type': 'cultivator', 'text': '你遇见一位同样在此探索的修士。'}
    elif etype == 'fortune':
        event = {'type': 'fortune', 'text': '一道若隐若现的洞府轮廓浮现在山壁之间,似是前辈高人留下的造化。'}
    else:
        event = {'type': 'nothing', 'text': random.choice(MYSTIC_NOTHING_FLAVORS)}
    cur = run("""UPDATE mystic_sessions SET stamina=stamina-1, pending_event_json=?
                 WHERE id=? AND pending_event_json IS NULL AND stamina>0""",
              (json.dumps(event), session['id']))
    if cur.rowcount == 0:
        flash('先应对眼前之事,再继续前行', 'error')
    else:
        run("""INSERT INTO mystic_explore_log (char_id,day,session_id,depth,stamina_before,event_type,created_ts)
               VALUES (?,?,?,?,?,?,?)""",
            (char['id'], session['day'], session['id'], depth, session['stamina'], etype, now_ts()))
    return redirect(url_for('mystic_home'))

@app.route('/mystic/event/resolve', methods=['POST'])
@login_required
def mystic_event_resolve():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active' or not session['pending_event_json']:
        flash('并无待应对之事', 'error')
        return redirect(url_for('mystic_home'))
    event = json.loads(session['pending_event_json'])
    choice = request.form.get('choice')
    zone = MYSTIC_ZONES_BY_KEY[session['zone_key']]
    depth = session['depth']
    profile = _player_combat_profile(char)
    agility = profile['stats'].get('agility', 0)
    luck = profile['stats'].get('luck', 0)

    if event['type'] == 'beast' and choice == 'fight':
        return redirect(url_for('mystic_battle_start', monster_key=event['monster_key']))

    # 先把这条事件标记为已应对,拦住同一事件被并发重复结算(比如手抖连点、开两个页签)
    cur = run("UPDATE mystic_sessions SET pending_event_json=NULL WHERE id=? AND pending_event_json IS NOT NULL",
              (session['id'],))
    if cur.rowcount == 0:
        flash('此事已被应对过了', 'error')
        return redirect(url_for('mystic_home'))

    sealed, pending = session['sealed_loot_json'], session['pending_loot_json']
    msg = ''
    hp_delta = 0

    if event['type'] == 'beast':
        if choice == 'flee_charm' and session['escape_charms'] > 0:
            run("UPDATE mystic_sessions SET escape_charms=escape_charms-1 WHERE id=?", (session['id'],))
            msg = random.choice(MYSTIC_BEAST_FLEE_FLAVORS)
        else:
            msg = random.choice(MYSTIC_BEAST_AVOID_FLAVORS)

    elif event['type'] == 'herb':
        if choice == 'wait':
            chance = min(0.85, 0.5 + agility * 0.006 + luck * 0.01)
            if random.random() < chance:
                qty = random.randint(3, 4)
                pending = _mystic_loot_add(pending, materials={zone['material_key']: qty})
                msg = f"{random.choice(MYSTIC_HERB_WAIT_SUCCESS_FLAVORS)}得{zone['material_label']}×{qty}。"
            else:
                hp_delta = -_mystic_env_damage(profile, 5, depth)
                msg = f"{random.choice(MYSTIC_HERB_WAIT_FAIL_FLAVORS)}你仓促间受了些皮外伤(气血{hp_delta})。"
        else:
            pending = _mystic_loot_add(pending, materials={zone['material_key']: 1})
            msg = f"{random.choice(MYSTIC_HERB_QUICK_FLAVORS)}采得{zone['material_label']}×1,虽药性未足,却也稳妥。"

    elif event['type'] == 'satchel':
        if choice == 'open':
            trap_chance = 1 - mystic_trap_check_chance(agility) * 0.6
            if random.random() < trap_chance:
                qty = random.randint(2, 3)
                lingshi = random.randint(15, 30)
                pending = _mystic_loot_add(pending, reward={'lingshi': lingshi},
                                            materials={zone['material_key']: qty})
                msg = f"{random.choice(MYSTIC_SATCHEL_OPEN_SUCCESS_FLAVORS)}得灵石{lingshi}、{zone['material_label']}×{qty}。"
            else:
                hp_delta = -_mystic_env_damage(profile, 8, depth)
                msg = f"{random.choice(MYSTIC_SATCHEL_OPEN_FAIL_FLAVORS)}骤然反噬(气血{hp_delta})。"
        else:
            if random.random() < mystic_trap_check_chance(agility):
                pending = _mystic_loot_add(pending, materials={zone['material_key']: 1})
                msg = f"{random.choice(MYSTIC_SATCHEL_PEEK_SUCCESS_FLAVORS)}小心取出{zone['material_label']}×1。"
            else:
                msg = random.choice(MYSTIC_SATCHEL_PEEK_FAIL_FLAVORS)

    elif event['type'] == 'cultivator':
        if choice == 'cooperate':
            qty = random.randint(1, 2)
            pending = _mystic_loot_add(pending, materials={zone['material_key']: qty})
            msg = f"{random.choice(MYSTIC_CULTIVATOR_COOPERATE_FLAVORS)}你得{zone['material_label']}×{qty}。"
        elif choice == 'trade':
            cost = 30
            if not _spend(char['id'], 'lingshi', cost):
                flash('灵石不足,无法交易', 'error')
                return redirect(url_for('mystic_home'))
            char['lingshi'] -= cost
            pool = [MYSTIC_COMMON_MATERIAL_KEY, zone['material_key']]
            got = random.choice(pool)
            pending = _mystic_loot_add(pending, materials={got: 2})
            msg = random.choice(MYSTIC_CULTIVATOR_TRADE_FLAVORS).format(cost=cost, label=MATERIAL_LABELS.get(got, got))
        else:
            msg = random.choice(MYSTIC_CULTIVATOR_AVOID_FLAVORS)

    elif event['type'] == 'fortune':
        if choice == 'breakin':
            power = profile['stats']['attack'] + profile['stats']['defense'] + agility * 2
            threshold = combat_realm_power(zone['realm_req']) * 0.6
            success_chance = min(0.95, max(0.40, power / (power + threshold)))
            if random.random() < success_chance:
                pending = _mystic_loot_add(pending, materials={'artifact_soul_thread': 1})
                if char['artifact_core_bound'] and random.random() < 0.3:
                    pending = _mystic_loot_add(pending, materials={'embryo_core': 1})
                tpls = EQUIPMENT_DROP_TEMPLATES.get(session['zone_key'], [])
                base_msg = random.choice(MYSTIC_FORTUNE_BREAKIN_SUCCESS_FLAVORS)
                if tpls and random.random() < 0.35:
                    tpl = random.choice(tpls)
                    pending = _mystic_loot_add(pending, equipment_key=tpl['key'])
                    msg = f"{base_msg},更拾得{tpl['label']}!"
                else:
                    msg = f"{base_msg}。"
                if depth >= 3 and not session['hidden_unlocked'] and random.random() < MYSTIC_HIDDEN_UNLOCK_CHANCE:
                    run("UPDATE mystic_sessions SET hidden_unlocked=1 WHERE id=?", (session['id'],))
                    msg += ' 恍惚间,你窥见了一处更深的隐秘去处。'
                if (char['realm_idx'] == 8 and char['infant_stage'] >= 1 and not char['infant_trial_buff']
                        and random.random() < 0.4):
                    run("UPDATE characters SET infant_trial_buff=1 WHERE id=?", (char['id'],))
                    msg += ' 洞府中的造化似乎也削弱了你心底的魔念,渡劫时当更添几分把握。'
                if (session['zone_key'] == MYSTIC_ARTIFACT_CORE_TOP_ZONE and char['artifact_core_bound']
                        and char['artifact_core_quality'] != 'top' and random.random() < MYSTIC_ARTIFACT_CORE_TOP_CHANCE):
                    run("UPDATE characters SET artifact_core_quality='top' WHERE id=?", (char['id'],))
                    msg += f" 恍惚间,一道异光没入{char['artifact_core_name']},其品级骤然蜕变至超品!"
                    owner_title = title_for(char['join_seq'], char['gender'])
                    log_chronicle(f"{char['name']}({owner_title})的本命法宝{char['artifact_core_name']}"
                                  "于秘境中骤然蜕变至超品", major=True)
                if session['zone_key'] in UNIQUE_EQUIPMENT_ZONES and random.random() < UNIQUE_EQUIPMENT_DROP_CHANCE:
                    unique_keys = [t['key'] for t in UNIQUE_EQUIPMENT_TEMPLATES]
                    placeholders = ','.join('?' * len(unique_keys))
                    claimed = {r['item_key'] for r in q(
                        f"SELECT DISTINCT item_key FROM character_equipment WHERE item_key IN ({placeholders}) AND qty>0",
                        tuple(unique_keys))}
                    available_unique = [k for k in unique_keys if k not in claimed]
                    if available_unique:
                        got_key = random.choice(available_unique)
                        pending = _mystic_loot_add(pending, equipment_key=got_key)
                        got_label = EQUIPMENT_TEMPLATES_BY_KEY[got_key]['label']
                        owner_title = title_for(char['join_seq'], char['gender'])
                        for c in q("SELECT id FROM characters"):
                            send_system_mail(c['id'], '旷世奇珍',
                                              f"{char['name']}({owner_title})于秘境中觅得旷世奇珍——"
                                              f"{got_label},全宗独一份!",
                                              from_label='宗门公告')
                        log_chronicle(f"{char['name']}({owner_title})于秘境中觅得旷世奇珍——{got_label},全宗独一份",
                                      major=True)
                        msg += f" 你于机缘中觅得旷世奇珍——{got_label},全宗独一份!"
                fortune_drop = MYSTIC_ZONE_FORTUNE_DROP.get(session['zone_key'])
                if fortune_drop and random.random() < fortune_drop['chance']:
                    pending = _mystic_loot_add(pending, materials={fortune_drop['material']: 1})
                    msg += f" 冥冥之中,你竟窥得一缕{MATERIAL_LABELS[fortune_drop['material']]}的气息,收入囊中!"
            else:
                hp_delta = -_mystic_env_damage(profile, 15, depth)
                msg = f"{random.choice(MYSTIC_FORTUNE_BREAKIN_FAIL_FLAVORS)}你受创不轻(气血{hp_delta})。"
        elif choice == 'sacrifice':
            cost = {zone['material_key']: 3}
            if not _has_materials(char['id'], cost):
                flash(f"{zone['material_label']}不足3枚,无法献祭", 'error')
                return redirect(url_for('mystic_home'))
            _consume_materials(char['id'], cost)
            pending = _mystic_loot_add(pending, materials={'artifact_soul_thread': 1})
            msg = random.choice(MYSTIC_FORTUNE_SACRIFICE_FLAVORS).format(label=zone['material_label'])
        else:
            pending = _mystic_loot_add(pending, materials={zone['material_key']: 2})
            msg = random.choice(MYSTIC_FORTUNE_RETREAT_FLAVORS)

    else:  # nothing
        pending = _mystic_loot_add(pending, materials={MYSTIC_COMMON_MATERIAL_KEY: 1})
        msg = event['text'] + f" 你顺手收集了些许秘境雾尘。"

    new_hp = max(0, session['hp'] + hp_delta)
    run("UPDATE mystic_sessions SET pending_event_json=NULL, pending_loot_json=?, hp=? WHERE id=?",
        (pending, new_hp, session['id']))
    if new_hp <= 0:
        session = dict(session)
        session['sealed_loot_json'], session['pending_loot_json'] = sealed, pending
        return _mystic_faint(char, session)
    flash(msg, 'ok' if hp_delta >= 0 else 'error')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/deepen', methods=['POST'])
@login_required
def mystic_deepen():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    if session['pending_event_json']:
        flash('先应对眼前之事', 'error')
        return redirect(url_for('mystic_home'))
    if session['depth'] >= MYSTIC_DEPTH_MAX:
        flash('已至此秘境最深处', 'error')
        return redirect(url_for('mystic_home'))
    if session['depth'] >= 3 and not session['hidden_unlocked']:
        flash('尚未寻得隐藏区域的入口', 'error')
        return redirect(url_for('mystic_home'))
    run("UPDATE mystic_sessions SET depth=depth+1 WHERE id=?", (session['id'],))
    flash(f"你毅然深入{MYSTIC_DEPTH_LABELS[session['depth']+1]},危险与机缘皆随之增长。", 'ok')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/seal', methods=['POST'])
@login_required
def mystic_seal():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    pending = json.loads(session['pending_loot_json'] or '{}')
    if not pending:
        flash('尚无收获可封存', 'error')
        return redirect(url_for('mystic_home'))
    sealed = json.loads(session['sealed_loot_json'] or '{}')
    for k, v in pending.get('reward', {}).items():
        sealed.setdefault('reward', {})[k] = sealed.get('reward', {}).get(k, 0) + v
    for k, v in pending.get('materials', {}).items():
        sealed.setdefault('materials', {})[k] = sealed.get('materials', {}).get(k, 0) + v
    sealed.setdefault('equipment', []).extend(pending.get('equipment', []))
    run("UPDATE mystic_sessions SET sealed_loot_json=?, pending_loot_json='{}' WHERE id=?",
        (json.dumps(sealed), session['id']))
    flash('已将当前收获封存,即便日后有失,这部分也不会再折损。', 'ok')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/heal', methods=['POST'])
@login_required
def mystic_heal():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    if session['heal_uses'] >= MYSTIC_HEAL_USES_MAX:
        flash('本轮丹药已用尽,不可再恢复气血', 'error')
        return redirect(url_for('mystic_home'))
    if session['hp'] >= session['hp_max']:
        flash('气血已满', 'error')
        return redirect(url_for('mystic_home'))
    cost = 60
    if not _spend(char['id'], 'lingshi', cost):
        flash('灵石不足', 'error')
        return redirect(url_for('mystic_home'))
    new_hp = min(session['hp_max'], session['hp'] + round(session['hp_max'] * 0.3))
    run("UPDATE mystic_sessions SET hp=?, heal_uses=heal_uses+1 WHERE id=?", (new_hp, session['id']))
    flash(f"服丹调息,气血恢复至{new_hp}/{session['hp_max']}", 'ok')
    return redirect(url_for('mystic_home'))

@app.route('/mystic/retreat', methods=['POST'])
@login_required
def mystic_retreat():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    if session['pending_event_json']:
        flash('先应对眼前之事,再行撤退', 'error')
        return redirect(url_for('mystic_home'))
    return _mystic_end(char, session)

# ── 游历人间:长周期、轻操作、剧情驱动,不像秘境/闭关那样禁止其他操作——纯后台计时+惰性结算 ──
# 首版只做青石镇1个地区,验证核心循环,其余地区/多维声望/NPC关系/副业联动都留到验证通过后再做

def sync_travel_points(char):
    ts = char['travel_points_ts'] or char['created_ts']
    gained = (now_ts() - ts) * TRAVEL_POINTS_REGEN_PER_DAY // 86400
    if gained > 0:
        if char['travel_points'] < TRAVEL_POINTS_CAP:
            char['travel_points'] = min(TRAVEL_POINTS_CAP, char['travel_points'] + gained)
        char['travel_points_ts'] = now_ts()
        run("UPDATE characters SET travel_points=?, travel_points_ts=? WHERE id=?",
            (char['travel_points'], char['travel_points_ts'], char['id']))
    elif not char['travel_points_ts']:
        char['travel_points_ts'] = now_ts()
        run("UPDATE characters SET travel_points_ts=? WHERE id=?", (char['travel_points_ts'], char['id']))
    return char

def add_region_familiarity(char_id, region_key, amount):
    if not amount:
        return
    run("""INSERT INTO character_region_familiarity (char_id,region_key,familiarity) VALUES (?,?,?)
           ON CONFLICT(char_id,region_key) DO UPDATE SET familiarity=familiarity+excluded.familiarity""",
        (char_id, region_key, amount))

def _travel_check_requires(char, requires):
    if not requires:
        return True
    profile = _player_combat_profile(char)
    return profile['stats'].get(requires.get('stat'), 0) >= requires.get('min', 0)

def _travel_apply_effects(char_id, region_key, effects):
    effects = dict(effects or {})
    familiarity = effects.pop('familiarity', 0)
    material = effects.pop('material', None)
    if effects:
        apply_reward(char_id, effects)
    if familiarity:
        add_region_familiarity(char_id, region_key, familiarity)
    if material:
        for mk, qty in material.items():
            _grant_material(char_id, mk, qty)

def _travel_thread_status(char_id, thread_key):
    row = q("SELECT status FROM travel_threads WHERE char_id=? AND thread_key=?", (char_id, thread_key), one=True)
    return row['status'] if row else None

def _travel_choice_available(char_id, event):
    """带 starts_thread 的入口事件,该奇遇线一旦开始过(不论进展或结局)就不再重复抽到。"""
    for c in event['choices']:
        tk = c.get('starts_thread')
        if tk and _travel_thread_status(char_id, tk):
            return False
    return True

def _travel_pick_legendary(char_id, region_key):
    fam_row = q("SELECT familiarity FROM character_region_familiarity WHERE char_id=? AND region_key=?",
                (char_id, region_key), one=True)
    fam_val = fam_row['familiarity'] if fam_row else 0
    for e in TRAVEL_LEGENDARY_EVENTS.get(region_key, []):
        if _travel_thread_status(char_id, e['key']):
            continue
        if fam_val < e['requires_familiarity']:
            continue
        need = e.get('requires_thread_completed_any', [])
        if need and not any(_travel_thread_status(char_id, tk) == 'completed' for tk in need):
            continue
        return e
    return None

def _travel_legendary_chance(char_id, region_key):
    row = q("SELECT legendary_miss_streak FROM character_region_familiarity WHERE char_id=? AND region_key=?",
            (char_id, region_key), one=True)
    streak = row['legendary_miss_streak'] if row else 0
    return min(TRAVEL_LEGENDARY_CHANCE_CAP, TRAVEL_LEGENDARY_BASE_CHANCE + streak * TRAVEL_LEGENDARY_CHANCE_STEP)

def _travel_roll_event(char, region_key, duration=None, force_special=False):
    """duration 传入本趟的 TRAVEL_DURATIONS 档位,拿 choice_weight_mult 调权重;
    force_special=True 时(云游四方保底特殊事件)直接把即时见闻踢出候选池,不会抽到纯水的见闻。"""
    char_id = char['id']
    legendary = _travel_pick_legendary(char_id, region_key)
    if legendary:
        chance = _travel_legendary_chance(char_id, region_key)
        if random.random() < chance:
            return legendary, 'legendary'
        run("""INSERT INTO character_region_familiarity (char_id,region_key,familiarity,legendary_miss_streak)
               VALUES (?,?,0,1)
               ON CONFLICT(char_id,region_key) DO UPDATE SET legendary_miss_streak=legendary_miss_streak+1""",
            (char_id, region_key))
    instant_pool = TRAVEL_INSTANT_EVENTS.get(region_key, [])
    choice_pool = [e for e in TRAVEL_CHOICE_EVENTS.get(region_key, []) if _travel_choice_available(char_id, e)]
    danger_pool = TRAVEL_DANGER_EVENTS.get(region_key, [])
    choice_weight = TRAVEL_CHOICE_WEIGHT * ((duration or {}).get('choice_weight_mult') or 1.0)
    fam_row = q("SELECT familiarity FROM character_region_familiarity WHERE char_id=? AND region_key=?",
                (char_id, region_key), one=True)
    if fam_row and fam_row['familiarity'] >= TRAVEL_FAMILIARITY_CHOICE_BOOST_THRESHOLD:
        choice_weight *= TRAVEL_FAMILIARITY_CHOICE_BOOST_MULT
    choice_weight = max(1, round(choice_weight))
    pool = [(e, 'choice') for e in choice_pool] * choice_weight + \
           [(e, 'danger') for e in danger_pool] * TRAVEL_DANGER_WEIGHT
    if not force_special:
        pool += [(e, 'instant') for e in instant_pool] * TRAVEL_INSTANT_WEIGHT
    if not pool:
        pool = [(e, 'instant') for e in instant_pool]
    return random.choice(pool)

def _travel_thread_label(thread_key):
    if thread_key in TRAVEL_THREADS:
        return TRAVEL_THREADS[thread_key]['label']
    if thread_key in TRAVEL_LEGENDARY_EVENTS_BY_KEY:
        return '传说奇遇'
    return thread_key

def _travel_advance(char):
    """惰性推进:游历中若到了下一事件槽位且当前没有待应对事件,抽一条新的;
    即时见闻/传说奇遇当场结算,选择事件挂起等待应对(见 travel_event_resolve)。"""
    session = q("SELECT * FROM travel_sessions WHERE char_id=?", (char['id'],), one=True)
    if not session or session['pending_event_json']:
        return session
    if now_ts() < session['next_event_ts'] or session['events_done'] >= session['events_total']:
        return session
    region_key = session['region_key']
    duration = TRAVEL_DURATIONS_BY_KEY.get(session['duration_key'], {})
    is_last_slot = session['events_done'] == session['events_total'] - 1
    force_special = bool(duration.get('guarantee_special') and is_last_slot and not session['had_special_event'])
    event, kind = _travel_roll_event(char, region_key, duration=duration, force_special=force_special)
    interval = (session['ends_ts'] - session['started_ts']) // (session['events_total'] + 1)
    next_ts = session['next_event_ts'] + interval
    special_flag = 1 if (kind in ('choice', 'danger', 'legendary') or session['had_special_event']) else 0
    if kind in ('instant', 'legendary'):
        effects = event['reward'] if kind == 'instant' else event['effects']
        _travel_apply_effects(char['id'], region_key, effects)
        if kind == 'legendary':
            run("INSERT OR IGNORE INTO travel_threads (char_id,thread_key,node_key,status,updated_ts) "
                "VALUES (?,?,?,?,?)", (char['id'], event['key'], 'done', 'completed', now_ts()))
            send_system_mail(char['id'], '奇遇天成', event['text'], from_label='游历见闻')
            title = title_for(char['join_seq'], char['gender'])
            region_label = TRAVEL_REGIONS_BY_KEY.get(region_key, {}).get('label', region_key)
            log_chronicle(f"{char['name']}({title})游历{region_label}时触发传说奇遇:{event['text']}", major=True)
        log = json.loads(session['log_json'] or '[]')
        log.append(event['text'])
        run("""UPDATE travel_sessions SET events_done=events_done+1, next_event_ts=?, log_json=?,
               had_special_event=? WHERE char_id=? AND pending_event_json IS NULL""",
            (next_ts, json.dumps(log), special_flag, char['id']))
    else:
        payload = {'kind': kind, **event}
        run("""UPDATE travel_sessions SET pending_event_json=?, had_special_event=?
               WHERE char_id=? AND pending_event_json IS NULL""",
            (json.dumps(payload), special_flag, char['id']))
    return q("SELECT * FROM travel_sessions WHERE char_id=?", (char['id'],), one=True)

@app.route('/travel')
@login_required
def travel_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_travel_points(char)
    my_rescue_call = q("SELECT * FROM travel_rescue_calls WHERE char_id=? ORDER BY id DESC LIMIT 1",
                        (char['id'],), one=True)
    if my_rescue_call and my_rescue_call['status'] == 'open':
        _travel_rescue_resolve_expiry(dict(my_rescue_call))
    session = _travel_advance(char)
    pending = json.loads(session['pending_event_json']) if session and session['pending_event_json'] else None
    ready_thread_nodes = []
    if not pending:
        due = q("SELECT * FROM travel_threads WHERE char_id=? AND status='waiting' AND ready_ts<=?",
                (char['id'], now_ts()))
        for row in due:
            run("UPDATE travel_threads SET status='ready' WHERE char_id=? AND thread_key=?",
                (char['id'], row['thread_key']))
        ready_rows = q("SELECT * FROM travel_threads WHERE char_id=? AND status='ready'", (char['id'],))
        for row in ready_rows:
            thread_def = TRAVEL_THREADS.get(row['thread_key'])
            node = thread_def['nodes'].get(row['node_key']) if thread_def else None
            if node:
                ready_thread_nodes.append({'thread_key': row['thread_key'],
                                            'thread_label': thread_def['label'], 'node': node})
    can_finish = bool(session and not pending and session['events_done'] >= session['events_total']
                       and now_ts() >= session['ends_ts'])
    regions = [dict(r, unlocked=char['realm_idx'] >= r['realm_req'], realm_name=REALMS[r['realm_req']]['name'])
               for r in TRAVEL_REGIONS]
    stats = _player_combat_profile(char)['stats']
    log_entries = json.loads(session['log_json']) if session and session['log_json'] else []
    trip_seconds_left = max(0, session['ends_ts'] - now_ts()) if session else 0
    return render_template('travel.html', char=char, trip=session, pending=pending, log_entries=log_entries,
                            ready_thread_nodes=ready_thread_nodes, can_finish=can_finish,
                            regions=regions, durations=TRAVEL_DURATIONS, stats=stats,
                            TRAVEL_REGIONS_BY_KEY=TRAVEL_REGIONS_BY_KEY,
                            TRAVEL_DURATIONS_BY_KEY=TRAVEL_DURATIONS_BY_KEY, trip_seconds_left=trip_seconds_left,
                            severe_injury=in_severe_injury(char),
                            severe_injury_remaining=max(0, (char['severe_injury_until_ts'] or 0) - now_ts()),
                            TRAVEL_POINTS_CAP=TRAVEL_POINTS_CAP)

@app.route('/travel/start/<region_key>/<duration_key>', methods=['POST'])
@login_required
def travel_start(region_key, duration_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if in_severe_injury(char):
        flash('你身负重伤,尚需静养,伤愈后再来', 'error')
        return redirect(url_for('home'))
    region = TRAVEL_REGIONS_BY_KEY.get(region_key)
    duration = TRAVEL_DURATIONS_BY_KEY.get(duration_key)
    if not region or not duration:
        flash('游历路线不存在', 'error')
        return redirect(url_for('travel_home'))
    if char['realm_idx'] < region['realm_req']:
        flash(f"修为不足,需达到 {REALMS[region['realm_req']]['name']}", 'error')
        return redirect(url_for('travel_home'))
    char = sync_travel_points(char)
    if q("SELECT 1 FROM travel_sessions WHERE char_id=?", (char['id'],), one=True):
        flash('你已在游历途中', 'error')
        return redirect(url_for('travel_home'))
    if char['travel_points'] < duration['cost']:
        flash('行程点数不足', 'error')
        return redirect(url_for('travel_home'))
    cur = run("UPDATE characters SET travel_points=travel_points-? WHERE id=? AND travel_points>=?",
              (duration['cost'], char['id'], duration['cost']))
    if cur.rowcount == 0:
        flash('行程点数不足', 'error')
        return redirect(url_for('travel_home'))
    ts = now_ts()
    ends_ts = ts + duration['hours'] * 3600
    interval = (ends_ts - ts) // (duration['event_slots'] + 1)
    run("""INSERT INTO travel_sessions (char_id,region_key,duration_key,started_ts,ends_ts,next_event_ts,
           events_done,events_total,pending_event_json,log_json)
           VALUES (?,?,?,?,?,?,0,?,NULL,'[]')""",
        (char['id'], region_key, duration_key, ts, ends_ts, ts + interval, duration['event_slots']))
    flash(f"启程前往{region['label']},{duration['label']}", 'ok')
    return redirect(url_for('travel_home'))

@app.route('/travel/event/resolve', methods=['POST'])
@login_required
def travel_event_resolve():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = q("SELECT * FROM travel_sessions WHERE char_id=?", (char['id'],), one=True)
    if not session or not session['pending_event_json']:
        flash('并无待应对之事', 'error')
        return redirect(url_for('travel_home'))
    payload = json.loads(session['pending_event_json'])
    choice_key = request.form.get('choice')

    if payload['kind'] == 'danger':
        if choice_key not in ('fight', 'rescue', 'flee'):
            flash('选择无效', 'error')
            return redirect(url_for('travel_home'))
        cur = run("UPDATE travel_sessions SET pending_event_json=NULL "
                   "WHERE char_id=? AND pending_event_json IS NOT NULL", (char['id'],))
        if cur.rowcount == 0:
            flash('此事已被应对过了', 'error')
            return redirect(url_for('travel_home'))
        msg, level = _travel_resolve_danger(char, session, payload, choice_key)
        log = json.loads(session['log_json'] or '[]')
        log.append(payload['text'])
        interval = (session['ends_ts'] - session['started_ts']) // (session['events_total'] + 1)
        next_ts = session['next_event_ts'] + interval
        run("UPDATE travel_sessions SET events_done=events_done+1, next_event_ts=?, log_json=? WHERE char_id=?",
            (next_ts, json.dumps(log), char['id']))
        check_achievements(char['id'])
        flash(msg, level)
        return redirect(url_for('travel_home'))

    choice = next((c for c in payload.get('choices', []) if c['key'] == choice_key), None)
    if not choice:
        flash('选择无效', 'error')
        return redirect(url_for('travel_home'))
    if not _travel_check_requires(char, choice.get('requires')):
        flash('资质不足,无法选择此项', 'error')
        return redirect(url_for('travel_home'))
    cur = run("UPDATE travel_sessions SET pending_event_json=NULL WHERE char_id=? AND pending_event_json IS NOT NULL",
              (char['id'],))
    if cur.rowcount == 0:
        flash('此事已被应对过了', 'error')
        return redirect(url_for('travel_home'))

    success = random.random() <= choice.get('success_rate', 1.0)
    effects = choice.get('success', {}) if success else choice.get('fail', {})
    _travel_apply_effects(char['id'], session['region_key'], effects)
    if success and choice.get('starts_thread'):
        thread_key = choice['starts_thread']
        ready_ts = now_ts() + choice.get('delay_hours', 0) * 3600
        run("""INSERT INTO travel_threads (char_id,thread_key,node_key,status,ready_ts,updated_ts)
               VALUES (?,?,?,'waiting',?,?)
               ON CONFLICT(char_id,thread_key) DO UPDATE SET node_key=excluded.node_key,
               status='waiting', ready_ts=excluded.ready_ts, updated_ts=excluded.updated_ts""",
            (char['id'], thread_key, choice['next'], ready_ts, now_ts()))

    log = json.loads(session['log_json'] or '[]')
    log.append(payload['text'])
    interval = (session['ends_ts'] - session['started_ts']) // (session['events_total'] + 1)
    next_ts = session['next_event_ts'] + interval
    run("UPDATE travel_sessions SET events_done=events_done+1, next_event_ts=?, log_json=? WHERE char_id=?",
        (next_ts, json.dumps(log), char['id']))
    check_achievements(char['id'])
    flash('你做出了选择' if success else '事与愿违,未能如意', 'ok' if success else 'error')
    return redirect(url_for('travel_home'))

def _travel_resolve_danger(char, session, payload, choice_key):
    """遇险三选一:力战(power-check,不做回合制)/呼叫宗门求援(挂到全宗可见的求援列表)/设法脱身(安全但无收获)。"""
    region_key = session['region_key']
    if choice_key == 'rescue':
        if q("SELECT 1 FROM travel_rescue_calls WHERE char_id=? AND status='open'", (char['id'],), one=True):
            return ('你已经发出过一次求援信号,分身乏术,只能自己先想办法应付眼前这一遭。'), 'error'
        expires_ts = now_ts() + TRAVEL_RESCUE_WINDOW_SECONDS
        run("""INSERT INTO travel_rescue_calls (char_id,region_key,danger_key,danger_text,expires_ts,created_ts)
               VALUES (?,?,?,?,?,?)""",
            (char['id'], region_key, payload['key'], payload['text'], expires_ts, now_ts()))
        return (f"你点燃求援信号,静候师兄弟赶来相助(约{TRAVEL_RESCUE_WINDOW_SECONDS // 60}分钟内,"
                "过时会由宗门后备力量兜底救你)。"), 'ok'
    if choice_key == 'flee':
        _travel_apply_effects(char['id'], region_key, {'familiarity': 2})
        return '你见势不妙,当机立断脱身而去,有惊无险,倒也摸熟了这一带的地形。', 'ok'
    # fight
    profile = _player_combat_profile(char)
    power = _discipline_power_score(profile)
    threshold = combat_realm_power(TRAVEL_REGIONS_BY_KEY[region_key]['realm_req']) * payload['power_mult']
    chance = min(0.85, max(0.25, power / (power + threshold)))
    if random.random() < chance:
        effects = dict(TRAVEL_DANGER_FIGHT_WIN_EFFECTS)
        _travel_apply_effects(char['id'], region_key, effects)
        drop_msg = ''
        templates = TRAVEL_EQUIPMENT_TEMPLATES.get(region_key, [])
        if templates and random.random() < TRAVEL_EQUIPMENT_DROP_CHANCE:
            tpl = random.choice(templates)
            _inventory_grant(char['id'], 'gear', 1, tpl['key'])
            drop_msg = f",更意外拾得{tpl['label']}!"
        found_gift = _maybe_find_gift(char['id'], 'travel')
        if found_gift:
            drop_msg += f",还在人间得到「{found_gift['rarity_label']}·{found_gift['name']}」（{found_gift['trait_label']}）!"
        weapon_mastery, weapon_level_up = _gain_weapon_mastery(char)
        mastery_msg = ',' + _weapon_mastery_gain_text(weapon_mastery, weapon_level_up)
        return (f"{_discipline_flavor(weapon_mastery, 'victory')}你击退了对方,虚惊一场,反倒有所收获{drop_msg}{mastery_msg}",
                'loot' if drop_msg else 'ok')
    _apply_injury(char)
    run("UPDATE characters SET mind_state=MAX(0,mind_state-?) WHERE id=?",
        (TRAVEL_DANGER_FIGHT_LOSE_MIND_PENALTY, char['id']))
    return '你不敌对方,负伤脱身,着实吃了一记暗亏。', 'error'

def _travel_rescue_resolve_expiry(call):
    """惰性检查:求援窗口(30分钟)到了却还没被真人完成救援,由宗门后备力量兜底——
    永远有人来救,只是有时候是NPC不是真玩家,代价也压得更轻(见 TRAVEL_MINOR_INJURY_*)。
    若正有人认领在处理(claim_expires_ts未到),先让认领方处理完,不抢跑。"""
    if call['status'] != 'open' or now_ts() < call['expires_ts']:
        return call
    if call['claimed_by'] and now_ts() < (call['claim_expires_ts'] or 0):
        return call
    cur = run("UPDATE travel_rescue_calls SET status='expired', resolved_ts=? WHERE id=? AND status='open'",
              (now_ts(), call['id']))
    if cur.rowcount:
        run("UPDATE characters SET severe_injury_until_ts=?, mind_state=MAX(0,mind_state-?) WHERE id=?",
            (now_ts() + TRAVEL_MINOR_INJURY_HOURS * 3600, TRAVEL_MINOR_INJURY_MIND_PENALTY, call['char_id']))
        char_row = q("SELECT lingshi FROM characters WHERE id=?", (call['char_id'],), one=True)
        lost = min(TRAVEL_MINOR_INJURY_LINGSHI_COST, char_row['lingshi'] if char_row else 0)
        if lost > 0:
            run("UPDATE characters SET lingshi=MAX(0,lingshi-?) WHERE id=?", (lost, call['char_id']))
        cost_desc = f",还花了{lost}灵石延医送药" if lost else ''
        send_system_mail(call['char_id'], '同门及时赶到',
                          f"{call['danger_text']}正当你独力支撑之际,宗门后备弟子及时赶到助你脱离险境——"
                          f"只是耽误了些时候,接下来{TRAVEL_MINOR_INJURY_HOURS}小时需要静养"
                          f"(打坐、委托收益减半){cost_desc}。",
                          from_label='游历见闻')
        caller = q("SELECT name, join_seq, gender FROM characters WHERE id=?", (call['char_id'],), one=True)
        if caller:
            log_chronicle(f"{caller['name']}({title_for(caller['join_seq'], caller['gender'])})游历途中遇险,"
                           "宗门后备弟子及时赶到,有惊无险")
    return q("SELECT * FROM travel_rescue_calls WHERE id=?", (call['id'],), one=True)

@app.route('/travel/rescue/<int:call_id>/respond', methods=['POST'])
@login_required
def travel_rescue_respond(call_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    call = q("SELECT * FROM travel_rescue_calls WHERE id=?", (call_id,), one=True)
    if not call:
        flash('求援信息不存在', 'error')
        return redirect(url_for('home'))
    if call['char_id'] == char['id']:
        flash('不能救援自己', 'error')
        return redirect(url_for('home'))
    call = dict(_travel_rescue_resolve_expiry(dict(call)))
    if call['status'] != 'open':
        flash('这份求援已经结束了', 'error')
        return redirect(url_for('home'))
    claim_expires = now_ts() + TRAVEL_RESCUE_CLAIM_SECONDS
    cur = run("""UPDATE travel_rescue_calls SET claimed_by=?, claim_expires_ts=?
                 WHERE id=? AND status='open' AND (claimed_by IS NULL OR claim_expires_ts<?)""",
              (char['id'], claim_expires, call_id, now_ts()))
    if cur.rowcount == 0:
        flash('已经有人在赶去救援的路上了', 'error')
        return redirect(url_for('home'))
    flash(f"你认领了这份求援,{TRAVEL_RESCUE_CLAIM_SECONDS // 60}分钟内去完成救援判定,过时会释放给其他人", 'ok')
    return redirect(url_for('home'))

@app.route('/travel/rescue/<int:call_id>/complete', methods=['POST'])
@login_required
def travel_rescue_complete(call_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    call = q("SELECT * FROM travel_rescue_calls WHERE id=?", (call_id,), one=True)
    if (not call or call['status'] != 'open' or call['claimed_by'] != char['id']
            or now_ts() >= (call['claim_expires_ts'] or 0)):
        flash('认领已失效,可能超时或已被他人处理', 'error')
        return redirect(url_for('home'))
    danger = TRAVEL_DANGER_EVENTS_BY_KEY.get(call['danger_key'])
    region = TRAVEL_REGIONS_BY_KEY.get(call['region_key'], {})
    profile = _player_combat_profile(char)
    power = _discipline_power_score(profile)
    power_mult = (danger['power_mult'] if danger else 0.5) * (1 - TRAVEL_RESCUE_POWER_DISCOUNT_PCT / 100)
    threshold = combat_realm_power(region.get('realm_req', 0)) * power_mult
    chance = min(0.9, max(0.35, power / (power + threshold)))

    if random.random() >= chance:
        run("UPDATE travel_rescue_calls SET claimed_by=NULL, claim_expires_ts=0 WHERE id=? AND claimed_by=?",
            (call_id, char['id']))
        apply_reward(char['id'], TRAVEL_RESCUE_ATTEMPT_CONSOLATION)
        flash('你赶到时局面比想象中棘手,没能一举解围,认领已释放给其他人,不妨再试一次别的求援', 'error')
        return redirect(url_for('home'))

    cur = run("UPDATE travel_rescue_calls SET status='rescued', rescuer_id=?, resolved_ts=? "
              "WHERE id=? AND status='open' AND claimed_by=?", (char['id'], now_ts(), call_id, char['id']))
    if cur.rowcount == 0:
        flash('这份求援已经结束了', 'error')
        return redirect(url_for('home'))

    pair_key = f"rescue_pair_{min(char['id'], call['char_id'])}_{max(char['id'], call['char_id'])}"
    repeated = get_daily_counter(char['id'], pair_key) > 0
    bump_daily_counter(char['id'], pair_key)
    apply_reward(char['id'], TRAVEL_RESCUE_RESCUER_REPEAT_REWARD if repeated else TRAVEL_RESCUE_RESCUER_REWARD)
    apply_reward(call['char_id'], TRAVEL_RESCUE_CALLER_REWARD)
    rescuer_title = title_for(char['join_seq'], char['gender'])
    send_system_mail(call['char_id'], '有惊无险',
                      f"{char['name']}({rescuer_title})及时赶到,助你脱离了险境。",
                      from_label='游历见闻')
    caller = q("SELECT name, join_seq, gender FROM characters WHERE id=?", (call['char_id'],), one=True)
    if caller:
        log_chronicle(f"{char['name']}({rescuer_title})千里驰援,救下了游历途中遇险的"
                      f"{caller['name']}({title_for(caller['join_seq'], caller['gender'])})")
    check_achievements(char['id'])
    weapon_mastery, weapon_level_up = _gain_weapon_mastery(char)
    rescue_msg = ('你及时赶到,救下了同门' if not repeated else
                  '你又一次救下了同门(今日同一对已经互救过,这次贡献照给、声望不重复)')
    rescue_msg += '，' + _weapon_mastery_gain_text(weapon_mastery, weapon_level_up)
    flash(rescue_msg, 'ok')
    return redirect(url_for('home'))

@app.route('/travel/thread/resolve/<thread_key>', methods=['POST'])
@login_required
def travel_thread_resolve(thread_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    thread_row = q("SELECT * FROM travel_threads WHERE char_id=? AND thread_key=?", (char['id'], thread_key), one=True)
    if not thread_row or thread_row['status'] != 'ready':
        flash('并无待应对之事', 'error')
        return redirect(url_for('travel_home'))
    thread_def = TRAVEL_THREADS.get(thread_key)
    node = thread_def['nodes'].get(thread_row['node_key']) if thread_def else None
    if not node:
        flash('奇遇数据有误', 'error')
        return redirect(url_for('travel_home'))
    choice_key = request.form.get('choice')
    choice = next((c for c in node['choices'] if c['key'] == choice_key), None)
    if not choice:
        flash('选择无效', 'error')
        return redirect(url_for('travel_home'))
    if not _travel_check_requires(char, choice.get('requires')):
        flash('资质不足,无法选择此项', 'error')
        return redirect(url_for('travel_home'))
    cur = run("UPDATE travel_threads SET status='resolving' WHERE char_id=? AND thread_key=? AND status='ready'",
              (char['id'], thread_key))
    if cur.rowcount == 0:
        flash('此事已被应对过了', 'error')
        return redirect(url_for('travel_home'))

    region_key = thread_def['region']
    _travel_apply_effects(char['id'], region_key, choice.get('effects', {}))
    if choice.get('outcome'):
        run("UPDATE travel_threads SET status=?, last_choice_label=?, last_result_text=?, updated_ts=? "
            "WHERE char_id=? AND thread_key=?",
            (choice['outcome'], choice['label'], choice.get('result_text', ''), now_ts(), char['id'], thread_key))
        title = title_for(char['join_seq'], char['gender'])
        log_chronicle(f"{char['name']}({title}){choice.get('result_text', '')}")
    else:
        ready_ts = now_ts() + choice.get('delay_hours', 0) * 3600
        run("UPDATE travel_threads SET status='waiting', node_key=?, ready_ts=?, "
            "last_choice_label=?, last_result_text=?, updated_ts=? WHERE char_id=? AND thread_key=?",
            (choice['next'], ready_ts, choice['label'], choice.get('result_text', ''),
             now_ts(), char['id'], thread_key))
    check_achievements(char['id'])
    flash(choice.get('result_text') or '你做出了选择,静待后续', 'ok')
    return redirect(url_for('travel_home'))

@app.route('/travel/claim', methods=['POST'])
@login_required
def travel_claim():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = q("SELECT * FROM travel_sessions WHERE char_id=?", (char['id'],), one=True)
    if not session:
        flash('并未在游历途中', 'error')
        return redirect(url_for('travel_home'))
    if session['pending_event_json']:
        flash('先应对眼前之事,再行整理见闻', 'error')
        return redirect(url_for('travel_home'))
    if session['events_done'] < session['events_total'] or now_ts() < session['ends_ts']:
        flash('行程尚未结束', 'error')
        return redirect(url_for('travel_home'))
    region = TRAVEL_REGIONS_BY_KEY.get(session['region_key'])
    run("DELETE FROM travel_sessions WHERE char_id=?", (char['id'],))
    add_dao_progress(char['id'], 'freedom', daily_cap=1, counter_suffix='travel')
    title = title_for(char['join_seq'], char['gender'])
    log_chronicle(f"{char['name']}({title})游历{region['label']}归来,收获颇丰")
    flash(f"从{region['label']}整理见闻归来", 'ok')
    return redirect(url_for('travel_home'))

@app.route('/travel/journal')
@login_required
def travel_journal():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    threads = [dict(row, label=_travel_thread_label(row['thread_key']))
               for row in q("SELECT * FROM travel_threads WHERE char_id=? ORDER BY updated_ts DESC", (char['id'],))]
    fam_rows = q("SELECT * FROM character_region_familiarity WHERE char_id=?", (char['id'],))
    familiarity = {r['region_key']: r['familiarity'] for r in fam_rows}
    return render_template('travel_journal.html', char=char, threads=threads, familiarity=familiarity,
                            TRAVEL_REGIONS_BY_KEY=TRAVEL_REGIONS_BY_KEY,
                            TRAVEL_THREAD_STATUS_LABELS=TRAVEL_THREAD_STATUS_LABELS)

# ── 遭遇战:力战/智取/撤退开局决策 + 最多4回合(僵持可追击2回合)的轻量回合制,不做死亡 ─────

def _player_technique_key(char):
    peak_name = _technique_peak_name(char)
    pt = peak_technique(peak_name) if peak_name else None
    return pt['key'] if pt else None

def _weapon_style(char):
    weapon_key = char['equipped_weapon_key']
    weapon = EQUIPMENT_TEMPLATES_BY_KEY.get(weapon_key) if weapon_key else None
    return weapon['weapon_style'] if weapon else 'unarmed'

def _weapon_mastery_profile(char, style=None):
    style = style or _weapon_style(char)
    info = WEAPON_DISCIPLINES[style]
    row = q("SELECT mastery FROM character_weapon_masteries WHERE char_id=? AND weapon_style=?",
            (char['id'], style), one=True)
    mastery = row['mastery'] if row else 0
    level = weapon_discipline_level(mastery)
    next_threshold = WEAPON_MASTERY_THRESHOLDS[level + 1] if level + 1 < len(WEAPON_MASTERY_THRESHOLDS) else None
    bonus = weapon_discipline_bonus(style, mastery)
    bonus_desc = {
        'sword': f'攻击无视{bonus}%护体',
        'blade': f'敌方气血低于35%时伤害+{bonus}%',
        'spear': f'每场战斗首回合伤害+{bonus}%',
        'heavy': f'受到反击伤害-{bonus}%',
        'ranged': f'普通攻击额外回复{bonus}点灵力',
        'unarmed': f'最大气血+{bonus}%',
    }[style]
    active_style = _weapon_style(char)
    weapon = EQUIPMENT_TEMPLATES_BY_KEY.get(char['equipped_weapon_key']) if char['equipped_weapon_key'] else None
    weapon_label = (weapon['label'] if weapon and style == active_style else
                    ('拳脚' if style == 'unarmed' else f"{info['label']}兵刃"))
    return dict(info, key=style, mastery=mastery, level=level, title=WEAPON_MASTERY_TITLES[level],
                next_threshold=next_threshold, bonus=bonus, bonus_desc=bonus_desc, weapon_label=weapon_label)

def _discipline_flavor(discipline, event):
    pool = discipline.get(f'{event}_flavors') or []
    return random.choice(pool).format(weapon=discipline['weapon_label']) if pool else ''

def _weapon_mastery_gain_text(mastery, leveled):
    text = f"{mastery['label']}熟练+1"
    if leveled:
        text += f"，兵道突破至「{mastery['title']}」"
        level_flavor = _discipline_flavor(mastery, 'level')
        if level_flavor:
            text += f"——{level_flavor}"
    return text

def _gain_weapon_mastery(char):
    style = _weapon_style(char)
    before = _weapon_mastery_profile(char, style)
    run("""INSERT INTO character_weapon_masteries(char_id,weapon_style,mastery,updated_ts) VALUES(?,?,1,?)
           ON CONFLICT(char_id,weapon_style) DO UPDATE SET mastery=MIN(100,mastery+1),updated_ts=excluded.updated_ts""",
        (char['id'], style, now_ts()))
    after = _weapon_mastery_profile(char, style)
    return after, after['level'] > before['level']

def _discipline_power_score(profile):
    """无回合制战斗的统一战力值；兵道圆满最多带来约一成对应实战增益。"""
    stats = profile['stats']
    base = stats['attack'] + stats['defense'] + stats.get('agility', 0) * 2
    return base * (1 + profile['discipline']['bonus'] / 100)

def _discipline_simple_damage(profile, damage):
    """天魔等简化战斗没有护体/血线回合，折半折算兵道优势，避免某流派完全失效。"""
    return max(1, round(damage * (1 + profile['discipline']['bonus'] / 200)))

def _equipment_stats(char):
    """装备加成合计:本命法宝按境界+方向算,武器/防具/饰品是固定模板直接查表加总,
    秘宝(炼器尊者专属第五件)终身绑定,同样固定加成。"""
    total = {'attack': 0, 'defense': 0, 'agility': 0, 'luck': 0}
    if char['artifact_core_bound'] and char['artifact_core_orientation']:
        core = artifact_core_stat_bonus(char['artifact_core_level'], char['artifact_core_orientation'],
                                         char['artifact_core_quality'] or 'low')
        for k in ('attack', 'defense', 'agility'):
            total[k] += core.get(k, 0)
    for key in (char['equipped_weapon_key'], char['equipped_armor_key'], char['equipped_accessory_key']):
        if not key:
            continue
        tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(key)
        if not tpl:
            continue
        for k in ('attack', 'defense', 'agility', 'luck'):
            total[k] += tpl.get(k, 0)
    for gift_col in ('equipped_tassel_gift_id', 'equipped_jade_gift_id'):
        if char[gift_col]:
            total['attack'] += GIFT_EQUIP_ATTACK_BONUS
            total['defense'] += GIFT_EQUIP_DEFENSE_BONUS
    if char['equipped_trinket_key'] == FORGE_MASTER_TRINKET['key']:
        for k in ('attack', 'defense', 'agility', 'luck'):
            total[k] += FORGE_MASTER_TRINKET.get(k, 0)
    if char['talent_reinforce_count']:
        total['attack'] += char['talent_reinforce_count'] * PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS
        total['defense'] += char['talent_reinforce_count'] * PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS
    if char['equipped_pet_id']:
        pet_row = q("SELECT pet_key, level FROM character_pets WHERE id=?", (char['equipped_pet_id'],), one=True)
        if pet_row and pet_row['level'] >= pet_max_level(pet_row['pet_key']):
            total['attack'] += PET_MAX_LEVEL_COMBAT_ATTACK_BONUS
            total['defense'] += PET_MAX_LEVEL_COMBAT_DEFENSE_BONUS
    return total

def _dan_bonus(char):
    """金丹品质给的固定加成,凝丹成功那一刻定型,伴随终身(可花重金升炼换更高档)。"""
    if not char['dan_quality']:
        return {'attack': 0, 'defense': 0, 'exp_bonus_pct': 0}
    return DAN_QUALITIES[char['dan_quality']]['bonus']

def _shen_bonus(char):
    """化神品级给的固定加成,同凝丹一个思路。"""
    if not char['shen_quality']:
        return {'attack': 0, 'defense': 0, 'exp_bonus_pct': 0}
    return SHEN_QUALITIES[char['shen_quality']]['bonus']

def _bone_bonus(char):
    """仙骨给的固定战斗属性加成,同凝丹/化神品质一个思路。"""
    if not char['immortal_bone_key']:
        return {'attack': 0, 'defense': 0}
    return IMMORTAL_BONES[char['immortal_bone_key']]['bonus']

def _player_combat_profile(char):
    technique_key = _player_technique_key(char)
    base = PEAK_TECHNIQUES_BY_KEY.get(technique_key, {}) if technique_key else {}
    stats = combat_stats(char['realm_idx'], char['physique'], base.get('atk_mod', 1.0), base.get('def_mod', 1.0))
    equip = _equipment_stats(char)
    dan_bonus = _dan_bonus(char)
    shen_bonus = _shen_bonus(char)
    bone_bonus = _bone_bonus(char)
    pastlife_atk = PASTLIFE_COMBAT_ATTACK_BONUS if char['pastlife_key'] else 0
    pastlife_def = PASTLIFE_COMBAT_DEFENSE_BONUS if char['pastlife_key'] else 0
    stats['attack'] += (equip['attack'] + dan_bonus['attack'] + shen_bonus['attack'] + bone_bonus['attack']
                         + pastlife_atk + dao_bonus(char['id'], 'attack'))
    stats['defense'] += equip['defense'] + dan_bonus['defense'] + shen_bonus['defense'] + bone_bonus['defense'] + pastlife_def
    stats['agility'] = equip['agility'] + dao_bonus(char['id'], 'agility')
    stats['luck'] = equip['luck']
    discipline = _weapon_mastery_profile(char)
    if discipline['key'] == 'unarmed' and discipline['bonus']:
        stats['max_hp'] = round(stats['max_hp'] * (1 + discipline['bonus'] / 100))
    mastery = 0
    if technique_key:
        row = q("SELECT mastery FROM character_techniques WHERE char_id=? AND technique_key=?",
                (char['id'], technique_key), one=True)
        mastery = row['mastery'] if row else 0
    moves = technique_moves(technique_key) if technique_key else []
    unlocked = [m for m in moves if mastery >= m['unlock_mastery']]
    equipped = unlocked if len(unlocked) <= 3 else [unlocked[0], unlocked[len(unlocked) // 2], unlocked[-1]]
    discipline['battle_intro_text'] = random.choice(discipline['battle_intro']).format(weapon=discipline['weapon_label'])
    pet_assist = None
    if char['equipped_pet_id']:
        equipped_pet_row = q("SELECT pet_key, pet_name, level FROM character_pets WHERE id=?",
                              (char['equipped_pet_id'],), one=True)
        if equipped_pet_row:
            pet_pct = pet_bonus_pct(equipped_pet_row['level'], equipped_pet_row['pet_key'])
            pet_assist = {'label': equipped_pet_row['pet_name'] or PET_TYPES[equipped_pet_row['pet_key']]['label'],
                          'attack': round(stats['attack'] * pet_pct / 100)}
    return {'technique_key': technique_key, 'technique_label': base.get('label', '徒手搏击'),
            'basic_label': discipline['basic_label'],
            'stack_label': TECHNIQUE_MOVES.get(technique_key, {}).get('stack_label', '气势'),
            'stats': stats, 'mastery': mastery, 'moves': equipped, 'realm_idx': char['realm_idx'],
            'discipline': discipline, 'pet_assist': pet_assist}

def _flee_chance(char, monster):
    diff = char['realm_idx'] - monster['realm_idx']
    return max(0.4, min(0.95, 0.70 + diff * 0.05))

def _persuade_chance(char, monster):
    return persuade_chance(spirit_sense(char['realm_idx']), spirit_sense(monster['realm_idx']))

def _reveal_chance(char, monster):
    return reveal_chance(spirit_sense(char['realm_idx']), spirit_sense(monster['realm_idx']))

def _monster_reward(monster, mult=1.0):
    # 战利品算个人所得,走灵石而不是贡献——贡献是宗门功勋,不该从"自己打赢的架"里出
    base_lingshi = round(8 * (monster['realm_idx'] + 1) * mult)
    reward = {'lingshi': base_lingshi, 'exp': round(base_lingshi * 3)}
    for k, v in monster.get('bonus_reward', {}).items():
        reward[k] = reward.get(k, 0) + round(v * mult)
    return reward

_REWARD_LABELS = {'exp': '修为', 'contribution': '贡献', 'lingshi': '灵石', 'lifespan_years': '寿元',
                   'stamina': '体力', 'physique': '体魄', 'mind_state': '心境', 'reputation': '声望',
                   'xiaxia_fame': '侠名', 'tiandi_jinghua': '天地精华'}

def _reward_desc(reward):
    parts = []
    for k, v in reward.items():
        if k == 'materials':
            parts.append('、'.join(f"{MATERIAL_LABELS.get(mk, mk)}×{mq}" for mk, mq in v.items()))
        elif k == 'equipment':
            parts.append('、'.join(f"{EQUIPMENT_TEMPLATES_BY_KEY.get(ek, {}).get('label', ek)}×{eq}" for ek, eq in v.items()))
        else:
            parts.append(f"{_REWARD_LABELS.get(k, k)} {'+' if v >= 0 else ''}{v}")
    return '、'.join(parts)

def _apply_injury(char):
    run("UPDATE characters SET injury_until_ts=?, stamina=MAX(0,stamina-?), mind_state=MAX(0,mind_state-?) WHERE id=?",
        (now_ts() + INJURY_DURATION_SECONDS, INJURY_STAMINA_PENALTY, INJURY_MIND_PENALTY, char['id']))

def _tick_burn(state):
    """灼烧结算,不管玩家这回合做什么(哪怕遁走)都要烧,返回日志行(没有灼烧则为None)。"""
    if state.get('monster_burn_rounds', 0) <= 0:
        return None
    burn_dmg = state.get('monster_burn_dmg', 0)
    state['monster_hp'] = max(0, state['monster_hp'] - burn_dmg)
    state['monster_burn_rounds'] -= 1
    return f"丹火持续灼烧,造成{burn_dmg}点伤害"

def _tick_poison(state):
    """中毒结算(蛊毒山魈),同样不管玩家做什么都要发作,返回(日志行或None, 是否因此毙命)。"""
    if state.get('player_poison_rounds', 0) <= 0:
        return None, False
    poison_dmg = state.get('player_poison_dmg', 0)
    state['player_hp'] = max(0, state['player_hp'] - poison_dmg)
    state['player_poison_rounds'] -= 1
    return f"蛊毒发作,你损失{poison_dmg}点气血", state['player_hp'] <= 0

def _resolve_combat_round(profile, monster_def, state, action):
    """结算一回合:灼烧结算(若有)→玩家出手→判定敌方特殊能力→敌方反击。返回(state, log列表, result)。
    result: None(继续) / 'win' / 'loss' / 'round_limit'。"""
    log = []
    burn_log = _tick_burn(state)
    if burn_log:
        log.append(burn_log)
        if state['monster_hp'] <= 0:
            return state, log, 'win'
    poison_log, poison_lethal = _tick_poison(state)
    if poison_log:
        log.append(poison_log)
        if poison_lethal:
            return state, log, 'loss'
    move = None
    self_reduce_pct = 0
    ignore_pct = 0
    discipline = profile['discipline']
    target_was_bloodied = state['monster_hp'] <= state['monster_max_hp'] * 0.35
    if action == 'basic':
        state['player_stacks'] = min(COMBAT_STACK_MAX, state.get('player_stacks', 0) + 1)
        ranged_regen = discipline['bonus'] if discipline['key'] == 'ranged' else 0
        state['player_mp'] = min(COMBAT_MP_START, state['player_mp'] + COMBAT_BASIC_MP_REGEN + ranged_regen)
        power_mult = 1.0
        state['wolf_basic_streak'] = state.get('wolf_basic_streak', 0) + 1
    elif action == 'defend':
        state['player_mp'] = min(COMBAT_MP_START, state['player_mp'] + COMBAT_DEFEND_MP_REGEN)
        self_reduce_pct = COMBAT_DEFEND_DAMAGE_REDUCTION_PCT
        power_mult = 0
        state['wolf_basic_streak'] = 0
    else:
        move = next((m for m in profile['moves'] if m['key'] == action), None)
        if not move or state['player_mp'] < move['mp_cost']:
            move = None
            power_mult = 0.6  # 招式无效(灵力不足等)时退化为一次弱攻击,不浪费整个回合
        else:
            state['player_mp'] -= move['mp_cost']
            power_mult = move['power_mult']
            if move['effect'] == 'ignore_defense':
                ignore_pct = move['effect_value']
            elif move['effect'] == 'self_reduce':
                self_reduce_pct = move['effect_value']
            state['wolf_basic_streak'] = 0

    if power_mult and discipline['key'] == 'sword':
        ignore_pct += discipline['bonus']
    if discipline['key'] == 'heavy':
        self_reduce_pct += discipline['bonus']

    if state.get('monster_ability') == 'weaken_round2' and state['round'] >= 2:
        power_mult *= 0.7

    hits = move['effect_value'] if (move and move['effect'] == 'multi_hit') else 1
    total_dmg = sum(
        combat_damage(profile['stats']['attack'], power_mult, state['monster_defense'],
                       profile['realm_idx'], ignore_pct)
        for _ in range(hits)) if power_mult else 0
    if total_dmg and discipline['key'] == 'spear' and state['round'] == 1:
        total_dmg = round(total_dmg * (1 + discipline['bonus'] / 100))
        if discipline['bonus']:
            log.append(f"枪出如龙，先手伤害+{discipline['bonus']}%")
    if total_dmg and discipline['key'] == 'blade' and target_was_bloodied:
        total_dmg = round(total_dmg * (1 + discipline['bonus'] / 100))
        if discipline['bonus']:
            log.append(f"刀势乘隙而入，追斩伤害+{discipline['bonus']}%")
    if move and move['effect'] == 'consume_stacks':
        total_dmg = round(total_dmg * (1 + state.get('player_stacks', 0) * move['effect_value'] / 100))
        state['player_stacks'] = 0
    if state.get('monster_ability') == 'first_move_halved' and move and not state.get('lizard_first_move_used'):
        total_dmg = round(total_dmg / 2)
        state['lizard_first_move_used'] = True
    if state.get('pursuing'):
        total_dmg = round(total_dmg * COMBAT_PURSUIT_DAMAGE_MULT)

    state['monster_hp'] = max(0, state['monster_hp'] - total_dmg)
    action_label = move['label'] if move else ('凝神守御' if action == 'defend' else profile['basic_label'])
    if total_dmg and not move and action != 'defend':
        log.append(f"{_discipline_flavor(discipline, 'basic')}造成{total_dmg}点伤害")
    else:
        log.append(f"你使出{action_label},造成{total_dmg}点伤害" if total_dmg else f"你{action_label}")
    if move and move['effect'] == 'heal_hp' and total_dmg:
        healed = round(total_dmg * move['effect_value'] / 100)
        state['player_hp'] = min(state['player_max_hp'], state['player_hp'] + healed)
        log.append(f"气血回复{healed}点")
    if move and move['effect'] == 'dot' and total_dmg:
        state['monster_burn_dmg'] = round(total_dmg * move['effect_value'] / 100)
        state['monster_burn_rounds'] = 2
        log.append(f"点燃丹火,未来2回合每回合追加{state['monster_burn_dmg']}点灼烧伤害")
    if state.get('monster_ability') == 'reflect' and total_dmg:
        reflect_dmg = round(total_dmg * 0.15)
        state['player_hp'] = max(0, state['player_hp'] - reflect_dmg)
        log.append(f"{state['monster_label']}体表反震,你被弹回{reflect_dmg}点伤害")
        if state['player_hp'] <= 0:
            return state, log, 'loss'
    pet_assist = profile.get('pet_assist')
    if pet_assist and state['monster_hp'] > 0 and random.random() < PET_ASSIST_CHANCE:
        assist_dmg = combat_damage(pet_assist['attack'], 1.0, state['monster_defense'], profile['realm_idx'])
        state['monster_hp'] = max(0, state['monster_hp'] - assist_dmg)
        log.append(f"{pet_assist['label']}趁隙助战,追加{assist_dmg}点伤害")
    if state['monster_hp'] <= 0:
        return state, log, 'win'

    monster_ability = state.get('monster_ability')
    counter_mult = 1.0
    counter_ignore_pct = 0
    if monster_ability == 'enrage_after_2_basic' and state.get('wolf_basic_streak', 0) >= 2:
        counter_mult = 1.3
        state['wolf_basic_streak'] = 0
    if monster_ability == 'enrage_low_hp' and state['monster_hp'] <= state['monster_max_hp'] * 0.3:
        counter_mult *= 1.25
    if monster_ability == 'ambush_round1' and state['round'] == 1:
        counter_mult *= 1.3
    if monster_ability == 'ignore_player_defense':
        counter_ignore_pct = 20
    counter_dmg = combat_damage(state['monster_attack'], counter_mult, profile['stats']['defense'],
                                 state['monster_realm_idx'], counter_ignore_pct)
    if state.get('pursuing'):
        counter_dmg = round(counter_dmg * COMBAT_PURSUIT_DAMAGE_MULT)
    total_reduce_pct = self_reduce_pct
    if state.get('revealed') and state['round'] == 1:
        total_reduce_pct += REVEAL_ROUND1_DAMAGE_REDUCTION_PCT
    if total_reduce_pct:
        counter_dmg = round(counter_dmg * (1 - min(80, total_reduce_pct) / 100))
    state['player_hp'] = max(0, state['player_hp'] - counter_dmg)
    log.append(f"{state['monster_label']}反击,你受到{counter_dmg}点伤害")
    if monster_ability == 'lifesteal' and counter_dmg:
        healed = round(counter_dmg * 0.2)
        state['monster_hp'] = min(state['monster_max_hp'], state['monster_hp'] + healed)
        log.append(f"{state['monster_label']}以邪功吸血,回复{healed}点气血")
    if monster_ability == 'poison_player' and counter_dmg and not state.get('player_poisoned_once'):
        state['player_poison_dmg'] = round(counter_dmg * 0.15)
        state['player_poison_rounds'] = 2
        state['player_poisoned_once'] = True
        log.append(f"你已中蛊毒,未来2回合每回合再损失{state['player_poison_dmg']}点气血")
    if state['player_hp'] <= 0:
        return state, log, 'loss'

    state['round'] += 1
    limit = COMBAT_ROUND_LIMIT + (COMBAT_PURSUIT_ROUND_LIMIT if state.get('pursuing') else 0)
    if state['round'] > limit:
        return state, log, 'round_limit'
    return state, log, None

def _mystic_sync_hp(char_id, hp):
    session = _mystic_session_today(char_id)
    if session and session['status'] == 'active':
        run("UPDATE mystic_sessions SET hp=? WHERE id=?", (max(0, hp), session['id']))

def _battle_win(char, state):
    monster = MONSTERS.get(state['monster_key'], {'realm_idx': state['monster_realm_idx']})
    reward = _monster_reward(monster, mult=COMBAT_PURSUIT_REWARD_MULT if state.get('pursuing') else 1.0)
    tk = _player_technique_key(char)
    if tk:
        run("UPDATE character_techniques SET mastery=MIN(?,mastery+5) WHERE char_id=? AND technique_key=?",
            (TECHNIQUE_MASTERY_MAX, char['id'], tk))
    session = _mystic_session_today(char['id'])
    drops = []
    materials = {}
    if session:
        zone = MYSTIC_ZONES_BY_KEY[session['zone_key']]
        materials[zone['material_key']] = materials.get(zone['material_key'], 0) + 1
        drops.append(zone['material_label'])
        for material_key, chance in monster.get('material_drop', {}).items():
            if random.random() < chance:
                materials[material_key] = materials.get(material_key, 0) + 1
                drops.append(MATERIAL_LABELS[material_key])
        pending = _mystic_loot_add(session['pending_loot_json'], reward=reward, materials=materials)
        run("UPDATE mystic_sessions SET pending_loot_json=?, hp=? WHERE id=?",
            (pending, state['player_hp'], session['id']))
        if zone['key'] == 'jiuyou' and not char['immortal_bone_key']:
            claimed = {r['immortal_bone_key'] for r in q(
                "SELECT immortal_bone_key FROM characters WHERE immortal_bone_key IS NOT NULL")}
            available = [k for k in JIUYOU_BONE_KEYS if k not in claimed]
            if available and random.random() < JIUYOU_BONE_DROP_CHANCE:
                bone_key = random.choice(available)
                run("UPDATE characters SET immortal_bone_key=? WHERE id=?", (bone_key, char['id']))
                char['immortal_bone_key'] = bone_key
                label = IMMORTAL_BONES[bone_key]['label']
                drops.append(f"旷世仙骨·{label}")
                title = title_for(char['join_seq'], char['gender'])
                for c in q("SELECT id FROM characters"):
                    send_system_mail(c['id'], '幽渊仙骨',
                                      f"{char['name']}于九幽渊中斩获妖物,觅得旷世仙骨——{label},全宗独一份!",
                                      from_label='宗门公告')
                log_chronicle(f"{char['name']}({title})于九幽渊中觅得{label}", major=True)
    check_achievements(char['id'])
    weapon_mastery, weapon_level_up = _gain_weapon_mastery(char)
    add_dao_progress(char['id'], 'sword', daily_cap=5)
    msg = f"{_discipline_flavor(weapon_mastery, 'victory')}击败{state['monster_label']}!{_reward_desc(reward)}"
    if drops:
        msg += '、' + '、'.join(drops)
    found_gift = _maybe_find_gift(char['id'], 'mystic')
    if found_gift:
        msg += f"、秘境中得「{found_gift['rarity_label']}·{found_gift['name']}」（{found_gift['trait_label']}），已收入行囊"
    msg += '、' + _weapon_mastery_gain_text(weapon_mastery, weapon_level_up)
    flash(msg, 'ok')
    return redirect(url_for('mystic_home'))

def _battle_loss(char, state):
    session = _mystic_session_today(char['id'])
    if session:
        session = dict(session)
        session['hp'] = 0
        return _mystic_faint(char, session)
    _apply_injury(char)
    flash(f"不敌{state['monster_label']},负伤而归(体力-{INJURY_STAMINA_PENALTY}、心境-{INJURY_MIND_PENALTY},"
          f"伤势持续2小时,不影响修为)", 'error')
    return redirect(url_for('mystic_home'))

def _sign_state(state):
    payload = json.dumps(state, sort_keys=True)
    sig = hmac.new(app.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload, sig

def _verify_state(payload, sig):
    """校验隐藏字段里的战斗状态没有被篡改;payload/sig 对不上就返回 None,调用方按"状态已失效"处理。"""
    if not payload or not sig:
        return None
    expected = hmac.new(app.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None

def _render_battle(char, profile, state, outcome=None, log=None):
    payload, sig = _sign_state(state)
    return render_template('battle.html', char=char, profile=profile, state=state,
                            state_json=payload, state_sig=sig, outcome=outcome, log=log or [])

@app.route('/mystic/battle/start/<monster_key>')
@login_required
def mystic_battle_start(monster_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    session = _mystic_session_today(char['id'])
    if not session or session['status'] != 'active':
        flash('尚未身处秘境', 'error')
        return redirect(url_for('mystic_home'))
    pending = json.loads(session['pending_event_json'] or 'null')
    if not pending or pending.get('type') != 'beast' or pending.get('monster_key') != monster_key:
        flash('对方已经离开了', 'error')
        return redirect(url_for('mystic_home'))
    monster_def = MONSTERS.get(monster_key)
    if not monster_def:
        flash('对方已经离开了', 'error')
        return redirect(url_for('mystic_home'))
    # 一旦真正迎战就把这场遭遇标记为已应对,重进/刷新此链接不会再换出一只满血的怪重新赌
    cur = run("UPDATE mystic_sessions SET pending_event_json=NULL WHERE id=? AND pending_event_json IS NOT NULL",
              (session['id'],))
    if cur.rowcount == 0:
        flash('对方已经离开了', 'error')
        return redirect(url_for('mystic_home'))
    m = encounter_monster_power(monster_key)
    profile = _player_combat_profile(char)
    danger_mult = MYSTIC_DEPTH_DANGER_MULT.get(session['depth'], 1.0)

    state = {
        'monster_key': monster_key, 'monster_label': m['label'],
        'monster_ability': m['ability'], 'monster_realm_idx': m['realm_idx'],
        'player_hp': session['hp'], 'player_max_hp': session['hp_max'],
        'player_mp': COMBAT_MP_START, 'player_stacks': 0,
        'monster_hp': round(m['max_hp'] * danger_mult), 'monster_max_hp': round(m['max_hp'] * danger_mult),
        'monster_attack': round(m['attack'] * danger_mult), 'monster_defense': m['defense'],
        'round': 1, 'wolf_basic_streak': 0, 'lizard_first_move_used': False, 'pursuing': False,
        'revealed': random.random() <= _reveal_chance(char, m),
    }
    return _render_battle(char, profile, state)

@app.route('/mystic/battle/round', methods=['POST'])
@login_required
def mystic_battle_round():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    state = _verify_state(request.form.get('state'), request.form.get('state_sig'))
    if state is None:
        flash('战斗状态已失效', 'error')
        return redirect(url_for('mystic_home'))
    action = request.form.get('action')
    monster_def = MONSTERS.get(state.get('monster_key'))
    if not monster_def:
        flash('对方已经离开了', 'error')
        return redirect(url_for('mystic_home'))
    profile = _player_combat_profile(char)
    session = _mystic_session_today(char['id'])

    if action == 'flee_charm':
        if not session or session['escape_charms'] <= 0:
            flash('并无遁符在身', 'error')
            return _render_battle(char, profile, state)
        run("UPDATE mystic_sessions SET escape_charms=escape_charms-1, hp=? WHERE id=?",
            (state['player_hp'], session['id']))
        flash(f"你掷出遁符,遁光一闪,已从{state['monster_label']}身旁脱身。", 'ok')
        return redirect(url_for('mystic_home'))

    if action == 'flee':
        agility_bonus = profile['stats'].get('agility', 0) * MYSTIC_AGILITY_ESCAPE_BONUS_PER_POINT
        if random.random() <= min(0.95, _flee_chance(char, monster_def) + agility_bonus):
            _mystic_sync_hp(char['id'], state['player_hp'])
            flash(f"你身法灵巧,成功摆脱了{state['monster_label']}", 'ok')
            return redirect(url_for('mystic_home'))
        flee_log = []
        burn_log = _tick_burn(state)
        if burn_log:
            flee_log.append(burn_log)
            if state['monster_hp'] <= 0:
                return _battle_win(char, state)
        poison_log, poison_lethal = _tick_poison(state)
        if poison_log:
            flee_log.append(poison_log)
            if poison_lethal:
                return _battle_loss(char, state)
        dmg = combat_damage(state['monster_attack'], 0.5, profile['stats']['defense'],
                             state['monster_realm_idx'], 0)
        state['player_hp'] = max(0, state['player_hp'] - dmg)
        flee_log.append(f"未能脱身,受到{dmg}点追击伤害")
        if state['player_hp'] <= 0:
            return _battle_loss(char, state)
        _mystic_sync_hp(char['id'], state['player_hp'])
        return _render_battle(char, profile, state, log=flee_log)

    state, log, result = _resolve_combat_round(profile, monster_def, state, action)
    if result == 'win':
        return _battle_win(char, state)
    if result == 'loss':
        return _battle_loss(char, state)
    _mystic_sync_hp(char['id'], state['player_hp'])
    if result == 'round_limit':
        return _render_battle(char, profile, state, outcome='round_limit', log=log)
    return _render_battle(char, profile, state, log=log)

@app.route('/mystic/battle/pursue', methods=['POST'])
@login_required
def mystic_battle_pursue():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    state = _verify_state(request.form.get('state'), request.form.get('state_sig'))
    if state is None:
        flash('战斗状态已失效', 'error')
        return redirect(url_for('mystic_home'))
    if request.form.get('choice') != 'pursue' or state.get('pursuing'):
        _mystic_sync_hp(char['id'], state['player_hp'])
        flash('你收手离开,全身而退', 'ok')
        return redirect(url_for('mystic_home'))
    state['pursuing'] = True
    profile = _player_combat_profile(char)
    return _render_battle(char, profile, state, log=['你选择继续追击!'])

# ── 装备:本命法宝(唯一绑定,方向+温养成长)+ 武器/防具/饰品(可替换,秘境掉落) ─────────────

@app.route('/equipment')
@login_required
def equipment_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = ensure_character_story(char)
    owned = [dict(r, label=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('label', r['item_key']),
                  slot=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('slot'),
                  zone=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('zone'),
                  element=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('element'),
                  usable=_weapon_usable(char, EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {})),
                  decompose_yield=EQUIPMENT_DECOMPOSE_YIELD.get(
                      EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('zone'), {'low': 2}))
             for r in q("SELECT * FROM character_equipment WHERE char_id=? AND qty>0", (char['id'],))]
    material_rows = q("SELECT * FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))
    materials_owned = {r['material_key']: r['qty'] for r in material_rows}
    preset_rows = {r['preset_key']: r for r in q(
        "SELECT * FROM character_equipment_presets WHERE char_id=?", (char['id'],))}
    presets = []
    for pk, default_label in EQUIPMENT_PRESET_DEFAULT_LABELS.items():
        row = preset_rows.get(pk)
        presets.append({
            'key': pk,
            'saved': bool(row),
            'label': row['label'] if row else default_label,
            'weapon_label': EQUIPMENT_TEMPLATES_BY_KEY.get(row['weapon_key'], {}).get('label') if row and row['weapon_key'] else None,
            'armor_label': EQUIPMENT_TEMPLATES_BY_KEY.get(row['armor_key'], {}).get('label') if row and row['armor_key'] else None,
            'accessory_label': EQUIPMENT_TEMPLATES_BY_KEY.get(row['accessory_key'], {}).get('label') if row and row['accessory_key'] else None,
            'is_current': bool(row and row['weapon_key'] == char['equipped_weapon_key']
                                and row['armor_key'] == char['equipped_armor_key']
                                and row['accessory_key'] == char['equipped_accessory_key']),
        })
    equip_locked = _equipment_locked(char)
    equipped_weapon_tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(char['equipped_weapon_key'])
    equipped = {
        'weapon': dict(equipped_weapon_tpl, usable=_weapon_usable(char, equipped_weapon_tpl)) if equipped_weapon_tpl else None,
        'armor': EQUIPMENT_TEMPLATES_BY_KEY.get(char['equipped_armor_key']),
        'accessory': EQUIPMENT_TEMPLATES_BY_KEY.get(char['equipped_accessory_key']),
    }
    active_weapon_style = _weapon_style(char)
    weapon_masteries = []
    for style in WEAPON_DISCIPLINES:
        profile = _weapon_mastery_profile(char, style)
        current_floor = WEAPON_MASTERY_THRESHOLDS[profile['level']]
        if profile['next_threshold']:
            span = profile['next_threshold'] - current_floor
            profile['progress_pct'] = max(0, min(100, (profile['mastery'] - current_floor) / span * 100))
        else:
            profile['progress_pct'] = 100
        profile['active'] = style == active_weapon_style
        weapon_masteries.append(profile)
    starter_weapons = [dict(t, owned=(char['equipped_weapon_key'] == t['key'] or
                                      _inventory_qty(char['id'], 'gear', t['key']) > 0),
                            usable=_weapon_usable(char, t),
                            discipline_label=WEAPON_DISCIPLINES[t['weapon_style']]['label'])
                       for t in SECT_STARTER_WEAPONS]
    core_quality = char['artifact_core_quality'] or 'low'
    core_bonus = artifact_core_stat_bonus(char['artifact_core_level'], char['artifact_core_orientation'], core_quality) \
        if char['artifact_core_bound'] else None
    equip_total = _equipment_stats(char)
    stable_upgrade = ARTIFACT_CORE_STABLE_UPGRADE_COSTS.get(core_quality)
    equipped_tassel = q("""SELECT g.gift_name, c.name maker_name FROM bond_gifts g
                           LEFT JOIN characters c ON c.id=g.maker_id WHERE g.id=?""",
                        (char['equipped_tassel_gift_id'],), one=True) if char['equipped_tassel_gift_id'] else None
    equipped_jade = q("""SELECT g.gift_name, c.name maker_name FROM bond_gifts g
                         LEFT JOIN characters c ON c.id=g.maker_id WHERE g.id=?""",
                      (char['equipped_jade_gift_id'],), one=True) if char['equipped_jade_gift_id'] else None
    return render_template('equipment.html', char=char, owned=owned, equipped=equipped,
                            equipped_tassel=equipped_tassel, equipped_jade=equipped_jade,
                            ELEMENTS=ELEMENTS, spirit_root_elements_label=spirit_root_elements_label,
                            core_bonus=core_bonus, equip_total=equip_total, core_quality=core_quality,
                            core_max_level=artifact_core_max_level(core_quality),
                            core_growth_title=artifact_growth_title(char['artifact_core_level'], char['artifact_core_orientation']),
                            EQUIPMENT_SLOTS=EQUIPMENT_SLOTS, EQUIPMENT_SLOT_LABELS=EQUIPMENT_SLOT_LABELS,
                            FORGE_MASTER_TRINKET=FORGE_MASTER_TRINKET,
                            ARTIFACT_CORE_ORIENTATIONS=ARTIFACT_CORE_ORIENTATIONS,
                            ARTIFACT_CORE_UNLOCK_REALM_IDX=ARTIFACT_CORE_UNLOCK_REALM_IDX,
                            ARTIFACT_CORE_QUALITIES=ARTIFACT_CORE_QUALITIES,
                            ARTIFACT_CORE_EXP_PER_LEVEL=ARTIFACT_CORE_EXP_PER_LEVEL,
                            ARTIFACT_CORE_NURTURE_MATERIAL_COST=ARTIFACT_CORE_NURTURE_MATERIAL_COST,
                            ARTIFACT_CORE_EQUIPMENT_NURTURE_EXP_GAIN=ARTIFACT_CORE_EQUIPMENT_NURTURE_EXP_GAIN,
                            ARTIFACT_CORE_RARE_NURTURE_MATERIAL_COST=ARTIFACT_CORE_RARE_NURTURE_MATERIAL_COST,
                            ARTIFACT_CORE_REFORGE_LINGSHI_COST=ARTIFACT_CORE_REFORGE_LINGSHI_COST,
                            ARTIFACT_REBIRTH_LINGSHI_COST=ARTIFACT_REBIRTH_LINGSHI_COST,
                            ARTIFACT_REBIRTH_MATERIAL_COST=ARTIFACT_REBIRTH_MATERIAL_COST,
                            ARTIFACT_REBIRTH_LEVEL_PENALTY_PCT=ARTIFACT_REBIRTH_LEVEL_PENALTY_PCT,
                            stable_upgrade=stable_upgrade,
                            stable_upgrade_ready=bool(stable_upgrade and char['lingshi'] >= stable_upgrade['lingshi']
                                                      and _has_materials(char['id'], stable_upgrade['materials'])),
                            MATERIAL_LABELS=MATERIAL_LABELS, realm_by_index=realm_by_index,
                            materials_owned=materials_owned, MATERIAL_TIERS=MATERIAL_TIERS,
                            MATERIAL_SYNTHESIZE_RATIO=MATERIAL_SYNTHESIZE_RATIO,
                            presets=presets, equip_locked=equip_locked,
                            weapon_masteries=weapon_masteries, active_weapon_style=active_weapon_style,
                            starter_weapons=starter_weapons, starter_weapon_cost=SECT_STARTER_WEAPON_COST)

@app.route('/equipment/starter_weapon/<item_key>', methods=['POST'])
@login_required
def equipment_starter_weapon(item_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    tpl = next((t for t in SECT_STARTER_WEAPONS if t['key'] == item_key), None)
    if not tpl:
        flash('兵器堂中没有这件武器', 'error')
        return redirect(url_for('equipment_home'))
    if char['equipped_weapon_key'] == item_key or _inventory_qty(char['id'], 'gear', item_key) > 0:
        flash(f"你已经领过{tpl['label']}", 'error')
        return redirect(url_for('equipment_home'))
    if not _weapon_usable(char, tpl):
        flash(f"你的灵根属性不合,驾驭不了{tpl['label']}", 'error')
        return redirect(url_for('equipment_home'))
    cur = run("UPDATE characters SET contribution=contribution-? WHERE id=? AND contribution>=?",
              (SECT_STARTER_WEAPON_COST, char['id'], SECT_STARTER_WEAPON_COST))
    if cur.rowcount == 0:
        flash(f"贡献不足，领取制式兵器需要{SECT_STARTER_WEAPON_COST}贡献", 'error')
        return redirect(url_for('equipment_home'))
    _inventory_grant(char['id'], 'gear', 1, item_key)
    flash(f"从兵器堂领得{tpl['label']}，可在下方武器库存中装备", 'ok')
    return redirect(url_for('equipment_home'))

def _equipment_locked(char):
    """秘境探索中,或游历途中有待应对事件时,不能换装/切换配装预设——避免中途临阵换将。"""
    if q("SELECT 1 FROM mystic_sessions WHERE char_id=? AND day LIKE ? AND status='active'",
         (char['id'], today_str() + '_%'), one=True):
        return True
    trip = q("SELECT pending_event_json FROM travel_sessions WHERE char_id=?", (char['id'],), one=True)
    if trip and trip['pending_event_json']:
        return True
    return False

def _weapon_usable(char, tpl):
    """武器带五行属性时,须与自身灵根属性匹配才能驾驭;天灵根五行皆通。"""
    return spirit_root_can_use_element(char['spirit_root'], char.get('spirit_root_elements'), tpl.get('element'))

def _equip_item_silent(char, slot, item_key):
    """不带flash的换装逻辑,给单件装备和配装预设复用。item_key为None时视为卸下该槽位。"""
    col = f'equipped_{slot}_key'
    current = char[col]
    if item_key:
        if _inventory_qty(char['id'], 'gear', item_key) < 1:
            return False
        if not _inventory_consume(char['id'], 'gear', 1, item_key):
            return False
    if current:
        _inventory_grant(char['id'], 'gear', 1, current)
    run(f"UPDATE characters SET {col}=? WHERE id=?", (item_key, char['id']))
    char[col] = item_key
    return True

@app.route('/equipment/equip/<slot>/<item_key>', methods=['POST'])
@login_required
def equipment_equip(slot, item_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if slot not in ('weapon', 'armor', 'accessory'):
        flash('该槽位不可替换', 'error')
        return redirect(url_for('equipment_home'))
    if _equipment_locked(char):
        flash('秘境探索中或游历途中有事待应对,暂不能换装', 'error')
        return redirect(url_for('equipment_home'))
    tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(item_key)
    if not tpl or tpl['slot'] != slot:
        flash('物品不存在', 'error')
        return redirect(url_for('equipment_home'))
    if slot == 'weapon' and not _weapon_usable(char, tpl):
        flash(f"你的灵根属性不合,驾驭不了{tpl['label']}", 'error')
        return redirect(url_for('equipment_home'))
    if not _equip_item_silent(char, slot, item_key):
        flash('你没有这件装备', 'error')
        return redirect(url_for('equipment_home'))
    discipline = _weapon_mastery_profile(char, tpl['weapon_style']) if slot == 'weapon' else None
    equip_flavor = _discipline_flavor(discipline, 'equip') if discipline else ''
    flash(f"已装备{tpl['label']}。{equip_flavor}" if equip_flavor else f"已装备{tpl['label']}", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/unequip/<slot>', methods=['POST'])
@login_required
def equipment_unequip(slot):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if slot not in ('weapon', 'armor', 'accessory'):
        flash('该槽位不可替换', 'error')
        return redirect(url_for('equipment_home'))
    if _equipment_locked(char):
        flash('秘境探索中或游历途中有事待应对,暂不能换装', 'error')
        return redirect(url_for('equipment_home'))
    if not char[f'equipped_{slot}_key']:
        flash('此槽位空空如也', 'error')
        return redirect(url_for('equipment_home'))
    _equip_item_silent(char, slot, None)
    if slot == 'weapon':
        unarmed = _weapon_mastery_profile(char, 'unarmed')
        flash(f"已卸下武器。{_discipline_flavor(unarmed, 'equip')}", 'ok')
    else:
        flash('已卸下', 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/preset/save/<preset_key>', methods=['POST'])
@login_required
def equipment_preset_save(preset_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if preset_key not in ('p1', 'p2', 'p3'):
        flash('预设槽位不存在', 'error')
        return redirect(url_for('equipment_home'))
    label = request.form.get('label', '').strip()[:20] or EQUIPMENT_PRESET_DEFAULT_LABELS.get(preset_key, preset_key)
    run("""INSERT INTO character_equipment_presets
           (char_id,preset_key,label,weapon_key,armor_key,accessory_key,updated_ts)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(char_id,preset_key) DO UPDATE SET label=excluded.label,
           weapon_key=excluded.weapon_key, armor_key=excluded.armor_key,
           accessory_key=excluded.accessory_key, updated_ts=excluded.updated_ts""",
        (char['id'], preset_key, label, char['equipped_weapon_key'], char['equipped_armor_key'],
         char['equipped_accessory_key'], now_ts()))
    flash(f"已将当前装备保存为「{label}」", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/preset/apply/<preset_key>', methods=['POST'])
@login_required
def equipment_preset_apply(preset_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if _equipment_locked(char):
        flash('秘境探索中或游历途中有事待应对,暂不能切换配装预设', 'error')
        return redirect(url_for('equipment_home'))
    preset = q("SELECT * FROM character_equipment_presets WHERE char_id=? AND preset_key=?",
               (char['id'], preset_key), one=True)
    if not preset:
        flash('这个预设还没保存过', 'error')
        return redirect(url_for('equipment_home'))
    skipped = []
    for slot, key in (('weapon', preset['weapon_key']), ('armor', preset['armor_key']),
                       ('accessory', preset['accessory_key'])):
        if key == char[f'equipped_{slot}_key']:
            continue
        tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(key) if key else None
        if key and slot == 'weapon' and tpl and not _weapon_usable(char, tpl):
            skipped.append(f"{tpl.get('label', key)}(灵根属性已不合)")
        elif key and not _equip_item_silent(char, slot, key):
            skipped.append(EQUIPMENT_TEMPLATES_BY_KEY.get(key, {}).get('label', key))
        elif not key:
            _equip_item_silent(char, slot, None)
    msg = f"已切换至配装「{preset['label']}」,不消耗任何资源"
    if skipped:
        msg += f",其中{'/'.join(skipped)}已不在你身上,该槽位维持原状"
    flash(msg, 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/decompose/<item_key>', methods=['POST'])
@login_required
def equipment_decompose(item_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(item_key)
    if not tpl:
        flash('物品不存在', 'error')
        return redirect(url_for('equipment_home'))
    if tpl.get('zone') in ('unique', 'sect'):
        flash('此物属于宗门制式配发，不可分解', 'error')
        return redirect(url_for('equipment_home'))
    if not _inventory_consume(char['id'], 'gear', 1, item_key):
        flash('你没有这件装备', 'error')
        return redirect(url_for('equipment_home'))
    yield_materials = EQUIPMENT_DECOMPOSE_YIELD.get(tpl.get('zone'), {'low': 2})
    for mk, qty in yield_materials.items():
        _grant_material(char['id'], mk, qty)
    yield_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in yield_materials.items())
    flash(f"分解{tpl['label']},得{yield_desc}", 'ok')
    return redirect(url_for('equipment_home'))

# ── 材料仓库:合成升级 / 秘境材料兑换 / 宗门捐献,给持续产出的材料找出口 ─────────────────

@app.route('/materials/synthesize/<tier>', methods=['POST'])
@login_required
def materials_synthesize(tier):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    idx = MATERIAL_TIERS.index(tier) if tier in MATERIAL_TIERS else -1
    if idx < 0 or idx >= len(MATERIAL_TIERS) - 1:
        flash('该材料无法再合成', 'error')
        return redirect(url_for('equipment_home'))
    next_tier = MATERIAL_TIERS[idx + 1]
    cost = {tier: MATERIAL_SYNTHESIZE_RATIO}
    if not _has_materials(char['id'], cost):
        flash(f"{MATERIAL_LABELS[tier]}不足{MATERIAL_SYNTHESIZE_RATIO}枚,无法合成", 'error')
        return redirect(url_for('equipment_home'))
    _consume_materials(char['id'], cost)
    _grant_material(char['id'], next_tier, 1)
    flash(f"以{MATERIAL_LABELS[tier]}×{MATERIAL_SYNTHESIZE_RATIO}合成{MATERIAL_LABELS[next_tier]}×1", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/materials/exchange/<key>', methods=['POST'])
@login_required
def material_shop_buy(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    item = MATERIAL_EXCHANGE_ITEMS_BY_KEY.get(key)
    if not item:
        flash('兑换项不存在', 'error')
        return redirect(url_for('shop_list'))
    counter_key = f"material_exchange_{key}"
    if get_daily_counter(char['id'], counter_key) >= SHOP_DAILY_LIMIT:
        flash('今日该项兑换已达上限', 'error')
        return redirect(url_for('shop_list'))
    if not _has_materials(char['id'], item['material_cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in item['material_cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('shop_list'))
    _consume_materials(char['id'], item['material_cost'])
    if item.get('reward'):
        apply_reward(char['id'], item['reward'])
    if item.get('material'):
        _grant_material(char['id'], item['material']['key'], item['material']['qty'])
    bump_daily_counter(char['id'], counter_key)
    flash(f"兑得{item['label']}", 'ok')
    return redirect(url_for('shop_list'))

@app.route('/materials/donate', methods=['POST'])
@login_required
def donate_material():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    tier = request.form.get('tier')
    qty = request.form.get('qty', type=int) or 0
    if tier not in DONATE_RATES or qty <= 0:
        flash('捐献参数有误', 'error')
        return redirect(url_for('peaks_list'))
    if not _has_materials(char['id'], {tier: qty}):
        flash(f"{MATERIAL_LABELS[tier]}不足{qty}枚", 'error')
        return redirect(url_for('peaks_list'))
    _consume_materials(char['id'], {tier: qty})
    gained = DONATE_RATES[tier] * qty
    run("UPDATE characters SET contribution=contribution+?, total_contribution=total_contribution+? WHERE id=?",
        (gained, gained, char['id']))
    flash(f"捐献{MATERIAL_LABELS[tier]}×{qty},得贡献 {gained}", 'ok')
    return redirect(url_for('peaks_list'))

@app.route('/equipment/artifact_core/bind', methods=['POST'])
@login_required
def artifact_core_bind():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['artifact_core_bound']:
        flash('本命法宝一旦绑定便终身相随,不可重复绑定', 'error')
        return redirect(url_for('equipment_home'))
    if char['realm_idx'] < ARTIFACT_CORE_UNLOCK_REALM_IDX:
        flash(f"修为不足,需达到 {REALMS[ARTIFACT_CORE_UNLOCK_REALM_IDX]['name']} 方可领取法宝胚胎", 'error')
        return redirect(url_for('equipment_home'))
    orientation = request.form.get('orientation')
    if orientation not in ARTIFACT_CORE_ORIENTATIONS:
        flash('请选择本命法宝的方向', 'error')
        return redirect(url_for('equipment_home'))
    core_name = roll_artifact_core_name(orientation)
    spirit = roll_artifact_spirit(orientation)
    run("UPDATE characters SET artifact_core_bound=1, artifact_core_orientation=?, artifact_core_level=0, "
        "artifact_core_exp=0, artifact_core_quality='low', artifact_core_name=?, artifact_core_spirit=? WHERE id=?",
        (orientation, core_name, spirit, char['id']))
    label = ARTIFACT_CORE_ORIENTATIONS[orientation]['label']
    flash(f"一枚无属性法宝胚胎与你血脉相融,自此终身相伴,得名「{core_name}」——你为其定下{label}之路,"
          f"尚是白板下品,静待温养,日后或可炼器升品,或于高阶秘境搏一场造化。", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/artifact_core/nurture', methods=['POST'])
@login_required
def artifact_core_nurture():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['artifact_core_bound']:
        flash('尚未绑定本命法宝', 'error')
        return redirect(url_for('equipment_home'))
    max_level = artifact_core_max_level(char['artifact_core_quality'] or 'low')
    if char['artifact_core_level'] >= max_level:
        flash('本命法宝已至当前品级的温养极限,可炼器升品或于高阶秘境搏一场造化', 'error')
        return redirect(url_for('equipment_home'))
    tier = request.form.get('tier', 'common')
    if tier == 'equipment':
        item_key = request.form.get('item_key', '')
        tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(item_key)
        if not tpl or tpl.get('zone') in ('unique', 'sect'):
            flash('此物不可用作温养辅料', 'error')
            return redirect(url_for('equipment_home'))
        if not _inventory_consume(char['id'], 'gear', 1, item_key):
            flash('你没有这件装备', 'error')
            return redirect(url_for('equipment_home'))
        gain = ARTIFACT_CORE_EQUIPMENT_NURTURE_EXP_GAIN
    else:
        cost = ARTIFACT_CORE_RARE_NURTURE_MATERIAL_COST if tier == 'rare' else ARTIFACT_CORE_NURTURE_MATERIAL_COST
        gain = ARTIFACT_CORE_RARE_NURTURE_EXP_GAIN if tier == 'rare' else ARTIFACT_CORE_NURTURE_EXP_GAIN
        if not _has_materials(char['id'], cost):
            cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in cost.items())
            flash(f"材料不足,需{cost_desc}", 'error')
            return redirect(url_for('equipment_home'))
        _consume_materials(char['id'], cost)
    new_exp = char['artifact_core_exp'] + gain
    new_level = char['artifact_core_level']
    leveled = False
    while new_level < max_level and new_exp >= ARTIFACT_CORE_EXP_PER_LEVEL:
        new_exp -= ARTIFACT_CORE_EXP_PER_LEVEL
        new_level += 1
        leveled = True
    run("UPDATE characters SET artifact_core_exp=?, artifact_core_level=? WHERE id=?",
        (new_exp, new_level, char['id']))
    add_dao_progress(char['id'], 'creation', daily_cap=5)
    msg = '温养本命法宝,略有精进'
    if leveled:
        msg += f",已至{new_level}层"
    flash(msg, 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/artifact_core/reforge', methods=['POST'])
@login_required
def artifact_core_reforge():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['artifact_core_bound']:
        flash('尚未绑定本命法宝', 'error')
        return redirect(url_for('equipment_home'))
    orientation = request.form.get('orientation')
    if orientation not in ARTIFACT_CORE_ORIENTATIONS:
        flash('请选择重铸后的方向', 'error')
        return redirect(url_for('equipment_home'))
    new_level = char['artifact_core_level'] * (100 - ARTIFACT_CORE_REFORGE_LEVEL_PENALTY_PCT) // 100
    cur = run("UPDATE characters SET lingshi=lingshi-?, artifact_core_orientation=?, artifact_core_level=?, "
              "artifact_core_exp=0 WHERE id=? AND lingshi>=?",
              (ARTIFACT_CORE_REFORGE_LINGSHI_COST, orientation, new_level, char['id'], ARTIFACT_CORE_REFORGE_LINGSHI_COST))
    if cur.rowcount == 0:
        flash('灵石不足', 'error')
        return redirect(url_for('equipment_home'))
    flash(f"本命法宝重铸,法脉转向{ARTIFACT_CORE_ORIENTATIONS[orientation]['label']},根基犹存但灵性折损,退至{new_level}层。", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/artifact_core/rebirth', methods=['POST'])
@login_required
def artifact_core_rebirth():
    char = me_character()
    if not char or not char['artifact_core_bound']:
        flash('尚未绑定本命法宝', 'error')
        return redirect(url_for('equipment_home'))
    orientation = request.form.get('orientation')
    if orientation not in ARTIFACT_CORE_ORIENTATIONS:
        flash('请选择炼形后的方向', 'error')
        return redirect(url_for('equipment_home'))
    if not _has_materials(char['id'], ARTIFACT_REBIRTH_MATERIAL_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in ARTIFACT_REBIRTH_MATERIAL_COST.items())
        flash(f"炼形所需不足：灵石{ARTIFACT_REBIRTH_LINGSHI_COST}、{cost_desc}", 'error')
        return redirect(url_for('equipment_home'))
    new_level = char['artifact_core_level'] * (100 - ARTIFACT_REBIRTH_LEVEL_PENALTY_PCT) // 100
    new_name = roll_artifact_core_name(orientation)
    new_spirit = roll_artifact_spirit(orientation)
    cur = run("""UPDATE characters SET lingshi=lingshi-?,artifact_core_orientation=?,artifact_core_level=?,
           artifact_core_name=?,artifact_core_spirit=? WHERE id=? AND lingshi>=?""",
        (ARTIFACT_REBIRTH_LINGSHI_COST, orientation, new_level, new_name, new_spirit, char['id'], ARTIFACT_REBIRTH_LINGSHI_COST))
    if cur.rowcount == 0:
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in ARTIFACT_REBIRTH_MATERIAL_COST.items())
        flash(f"炼形所需不足：灵石{ARTIFACT_REBIRTH_LINGSHI_COST}、{cost_desc}", 'error')
        return redirect(url_for('equipment_home'))
    _consume_materials(char['id'], ARTIFACT_REBIRTH_MATERIAL_COST)
    flash(f"转世炼形功成，法宝化为「{new_name}」，器灵性情{new_spirit}；品级保留，温养退至{new_level}层。", 'ok')
    return redirect(url_for('equipment_home'))

@app.route('/equipment/artifact_core/stable_upgrade', methods=['POST'])
@login_required
def artifact_core_stable_upgrade():
    char = me_character()
    if not char or not char['artifact_core_bound']:
        flash('尚未绑定本命法宝', 'error')
        return redirect(url_for('equipment_home'))
    current = char['artifact_core_quality'] or 'low'
    upgrade = ARTIFACT_CORE_STABLE_UPGRADE_COSTS.get(current)
    if not upgrade:
        flash('本命法宝已是超品，无需继续升阶', 'error')
        return redirect(url_for('equipment_home'))
    if not _has_materials(char['id'], upgrade['materials']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in upgrade['materials'].items())
        flash(f"升阶所需不足：灵石{upgrade['lingshi']}、{cost_desc}", 'error')
        return redirect(url_for('equipment_home'))
    cur = run("""UPDATE characters SET lingshi=lingshi-?,artifact_core_quality=? WHERE id=?
                 AND artifact_core_quality=? AND lingshi>=?""",
              (upgrade['lingshi'], upgrade['to'], char['id'], current, upgrade['lingshi']))
    if cur.rowcount == 0:
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in upgrade['materials'].items())
        flash(f"升阶所需不足：灵石{upgrade['lingshi']}、{cost_desc}", 'error')
        return redirect(url_for('equipment_home'))
    _consume_materials(char['id'], upgrade['materials'])
    new_label = ARTIFACT_CORE_QUALITIES[upgrade['to']]['label']
    flash(f"稳固升阶功成！{char['artifact_core_name']}晋为{new_label}，名字、器灵与全部温养层数均保留。", 'ok')
    return redirect(url_for('equipment_home'))

# ── 峰:固定8峰(7长老峰+1掌门峰),精英弟子拜师入峰,峰主出缺后由本峰弟子考核递补 ───────

@app.route('/peaks')
@login_required
def peaks_list():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    peaks = q("""SELECT peaks.*, elder.name elder_name, elder.realm_idx elder_realm_idx,
                        elder.join_seq elder_join_seq, elder.gender elder_gender, elder.is_npc elder_is_npc,
                        COUNT(m.id) disciple_count
                 FROM peaks LEFT JOIN characters elder ON elder.id = peaks.elder_id
                 LEFT JOIN characters m ON m.peak_id = peaks.id AND m.id IS NOT peaks.elder_id
                 GROUP BY peaks.id ORDER BY peaks.is_leader DESC, peaks.id""")
    can_join_peak = char['rank_tier'] == 3 and not char['peak_id']
    is_elder_anywhere = bool(q("SELECT 1 FROM peaks WHERE elder_id=?", (char['id'],), one=True))
    can_transfer = bool(char['peak_id']) and not char['peak_transferred'] and not is_elder_anywhere
    current_peak = q("SELECT * FROM peaks WHERE id=?", (char['peak_id'],), one=True) if char['peak_id'] else None
    transfer_cost = 0 if (current_peak and current_peak['is_leader']) else PEAK_TRANSFER_CONTRIBUTION_COST
    can_apply_leader = (char['rank_tier'] == 5 and not char['is_npc']
                         and not char['ascended'] and not char['deceased'])
    application_open = leader_application_open()
    return render_template('peaks.html', peaks=peaks, char=char, title_for=title_for,
                            can_join_peak=can_join_peak, max_disciples=MAX_DISCIPLES_PER_PEAK,
                            can_transfer=can_transfer, transfer_cost=transfer_cost,
                            can_apply_leader=can_apply_leader, application_open=application_open,
                            realm_by_index=realm_by_index, PEAK_SPECIALTIES=PEAK_SPECIALTIES)

@app.route('/peaks/apply_leader', methods=['POST'])
@login_required
def apply_leader():
    """掌门位空缺时申请即就任(先到先得);已有人在位则申请视为挑战,双方按战力算分+运气PK一场。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['is_npc'] or char['ascended'] or char['deceased']:
        flash('无法申请', 'error')
        return redirect(url_for('peaks_list'))
    if char['rank_tier'] != 5:
        flash('唯有在位长老方可申请继任掌门', 'error')
        return redirect(url_for('peaks_list'))
    if not leader_application_open():
        cfg = q("SELECT * FROM sect_config WHERE id=1", one=True)
        flash(f"{cfg['npc_leader_name']}道友尚未离宗,掌门之位暂不受理申请", 'error')
        return redirect(url_for('peaks_list'))
    lp = leader_peak()
    if not lp['elder_id']:
        cur = run("UPDATE peaks SET elder_id=? WHERE id=? AND elder_id IS NULL", (char['id'], lp['id']))
        if cur.rowcount == 0:
            flash('慢了一步,已有人抢先坐上掌门之位,可发起挑战', 'error')
            return redirect(url_for('peaks_list'))
        cfg = q("SELECT * FROM sect_config WHERE id=1", one=True)
        if not cfg['succession_done']:
            run("UPDATE sect_config SET succession_done=1 WHERE id=1")
        _install_leader(char, lp, f"{char['name']}主动请命,继任{SECT_NAME}掌门之位,坐镇{lp['name']}。")
        flash('申请通过,你已就任掌门!', 'ok')
        return redirect(url_for('peaks_list'))
    if lp['elder_id'] == char['id']:
        flash('你已是掌门', 'error')
        return redirect(url_for('peaks_list'))
    incumbent = dict(q("SELECT * FROM characters WHERE id=?", (lp['elder_id'],), one=True))
    challenger_power = _discipline_power_score(_player_combat_profile(char))
    incumbent_power = _discipline_power_score(_player_combat_profile(incumbent))
    chance = min(0.85, max(0.15, challenger_power / (challenger_power + incumbent_power)))
    if random.random() < chance:
        old_home = q("SELECT id FROM peaks WHERE elder_id=? AND is_leader=0", (incumbent['id'],), one=True)
        run("UPDATE characters SET rank_tier=5, peak_id=? WHERE id=?",
            (old_home['id'] if old_home else incumbent['peak_id'], incumbent['id']))
        _close_leader_reign(incumbent['id'], 'dethroned', defeated_by_char_id=char['id'])
        _install_leader(char, lp, f"{char['name']}力挫掌门{incumbent['name']},夺得{SECT_NAME}掌门之位,坐镇{lp['name']}。")
        flash(f"一番苦斗,你力挫{incumbent['name']},夺得掌门之位!", 'ok')
    else:
        flash(f"你向掌门{incumbent['name']}下战书,惜败一筹,{incumbent['name']}继续坐镇{lp['name']}", 'error')
    return redirect(url_for('peaks_list'))

@app.route('/peaks/<int:peak_id>/join', methods=['POST'])
@login_required
def peak_join(peak_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['rank_tier'] != 3:
        flash('只有精英弟子才能拜师入峰', 'error')
        return redirect(url_for('peaks_list'))
    if char['peak_id']:
        flash('你已拜入一峰,无法重复拜师', 'error')
        return redirect(url_for('peaks_list'))
    peak = q("SELECT * FROM peaks WHERE id=?", (peak_id,), one=True)
    if not peak:
        flash('该峰不存在', 'error')
        return redirect(url_for('peaks_list'))
    disciple_count = q("SELECT COUNT(*) c FROM characters WHERE peak_id=? AND id != ?",
                        (peak_id, peak['elder_id'] or -1), one=True)['c']
    if disciple_count >= MAX_DISCIPLES_PER_PEAK:
        flash('该峰弟子名额已满', 'error')
        return redirect(url_for('peaks_list'))
    run("UPDATE characters SET peak_id=? WHERE id=?", (peak_id, char['id']))
    pt = peak_technique(peak['name'])
    if pt:
        run("INSERT OR IGNORE INTO character_techniques (char_id,technique_key,learned_ts,mastery) "
            "VALUES (?,?,?,0)", (char['id'], pt['key'], now_ts()))
    if peak_specialty(peak['name']).get('alchemy'):
        for r in ALCHEMY_RECIPES:
            if r['unlock'] == 'starter':
                run("INSERT OR IGNORE INTO character_recipes (char_id,recipe_key,learned_ts) VALUES (?,?,?)",
                    (char['id'], r['key'], now_ts()))
    flash(f"已拜入{peak['name']}", 'ok')
    send_system_mail(char['id'], '入门指引·功法与洞府',
                      f"拜入{peak['name']}后,你自动习得了本峰专属功法,静室的打坐按钮里会多出这一项——"
                      "用得越多越熟练,境界越高效果也越好,不用刻意去练,正常打坐就会涨。"
                      "另外,洞府地图(首页「洞府」入口再进「地图」)现在能搬进本峰弟子居所了,"
                      "不搬也不影响修炼,想去时再去便是。同峰的师兄姐里若有看中的,"
                      "可到「拜师」页面正式拜入门下。",
                      from_label='宗门·执事堂')
    return redirect(url_for('peaks_list'))

@app.route('/peaks/<int:peak_id>/transfer', methods=['POST'])
@login_required
def peak_transfer(peak_id):
    """一生仅一次的转峰机会:原峰专属功法作废,需重新习得新峰功法。
    由掌门峰转出免费(视为纠错,凌霄峰本非精英弟子拜峰时的常规选项之一),其余转峰照常收贡献。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['peak_id']:
        flash('尚未拜入一峰,无从转峰', 'error')
        return redirect(url_for('peaks_list'))
    if char['peak_transferred']:
        flash('转峰机会一生仅有一次,你已用过', 'error')
        return redirect(url_for('peaks_list'))
    if peak_id == char['peak_id']:
        flash('这就是你当前所在的峰', 'error')
        return redirect(url_for('peaks_list'))
    if q("SELECT 1 FROM peaks WHERE elder_id=?", (char['id'],), one=True):
        flash('长老/掌门身份在身,无法转峰', 'error')
        return redirect(url_for('peaks_list'))
    old_peak = q("SELECT * FROM peaks WHERE id=?", (char['peak_id'],), one=True)
    peak = q("SELECT * FROM peaks WHERE id=?", (peak_id,), one=True)
    if not peak:
        flash('该峰不存在', 'error')
        return redirect(url_for('peaks_list'))
    disciple_count = q("SELECT COUNT(*) c FROM characters WHERE peak_id=? AND id != ?",
                        (peak_id, peak['elder_id'] or -1), one=True)['c']
    if disciple_count >= MAX_DISCIPLES_PER_PEAK:
        flash('该峰弟子名额已满', 'error')
        return redirect(url_for('peaks_list'))
    cost = 0 if old_peak['is_leader'] else PEAK_TRANSFER_CONTRIBUTION_COST
    if cost and not _spend(char['id'], 'contribution', cost):
        flash(f"贡献不足{cost},无法转峰", 'error')
        return redirect(url_for('peaks_list'))
    old_pt = peak_technique(old_peak['name'])
    if old_pt:
        run("DELETE FROM character_techniques WHERE char_id=? AND technique_key=?", (char['id'], old_pt['key']))
    run("UPDATE characters SET peak_id=?, peak_transferred=1 WHERE id=?", (peak_id, char['id']))
    pt = peak_technique(peak['name'])
    if pt:
        run("INSERT OR IGNORE INTO character_techniques (char_id,technique_key,learned_ts,mastery) "
            "VALUES (?,?,?,0)", (char['id'], pt['key'], now_ts()))
    if peak_specialty(peak['name']).get('alchemy'):
        for r in ALCHEMY_RECIPES:
            if r['unlock'] == 'starter':
                run("INSERT OR IGNORE INTO character_recipes (char_id,recipe_key,learned_ts) VALUES (?,?,?)",
                    (char['id'], r['key'], now_ts()))
    cost_desc = f"耗贡献{cost}," if cost else "(由掌门峰转出,免贡献)"
    flash(f"{cost_desc}转投{peak['name']},此前所修{old_peak['name']}专属功法已作废,需重新习得新峰功法", 'ok')
    return redirect(url_for('peaks_list'))

# ── 拜师:须先入峰,可拜同峰任意师兄姐(含峰主);NPC自动同意,玩家需双向确认。
# discipleships.disciple_id 唯一→每人至多一行,一生只认一位师父,除非师父身故才能重新择师;
# 师父飞升不解绑,名分终身保留。师父接受时须赐字、赠一件礼物(材料或装备)──────────────

def _mentor_row(disciple_id):
    return q("SELECT * FROM discipleships WHERE disciple_id=?", (disciple_id,), one=True)

@app.route('/mentor')
@login_required
def mentor_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    my_row = _mentor_row(char['id'])
    master = None
    pending_target = None
    if my_row and my_row['status'] == 'active':
        master = q("SELECT * FROM characters WHERE id=?", (my_row['master_id'],), one=True)
    elif my_row and my_row['status'] == 'pending':
        pending_target = q("SELECT * FROM characters WHERE id=?", (my_row['master_id'],), one=True)
    candidates = []
    if char['peak_id'] and not master and not pending_target:
        candidates = q("""SELECT * FROM characters
                           WHERE (peak_id=? OR id=(SELECT elder_id FROM peaks WHERE id=?))
                             AND id!=? AND deceased=0 AND ascended=0
                           ORDER BY realm_idx DESC, join_seq ASC""",
                       (char['peak_id'], char['peak_id'], char['id']))
    incoming = []
    for r in q("SELECT * FROM discipleships WHERE master_id=? AND status='pending'", (char['id'],)):
        proposer = q("SELECT * FROM characters WHERE id=?", (r['disciple_id'],), one=True)
        if proposer:
            incoming.append(proposer)
    my_materials = [dict(r, label=MATERIAL_LABELS.get(r['material_key'], r['material_key']))
                    for r in q("SELECT * FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))]
    my_gear = [dict(r, label=_market_item_label('gear', r['item_key']))
               for r in q("SELECT * FROM character_equipment WHERE char_id=? AND qty>0", (char['id'],))]
    consult_left = MENTOR_CONSULT_DAILY_LIMIT - get_daily_counter(char['id'], 'mentor_consult')
    disciples = q("""SELECT c.* FROM discipleships d
                       JOIN characters c ON c.id=d.disciple_id
                       WHERE d.master_id=? AND d.status='active' AND c.deceased=0 AND c.ascended=0
                       ORDER BY c.join_seq""", (char['id'],))
    train_left = MENTOR_TRAIN_DAILY_LIMIT - get_daily_counter(char['id'], 'mentor_train')
    return render_template('mentor.html', char=char, master=master, pending_target=pending_target,
                            candidates=candidates, incoming=incoming, disciples=disciples,
                            my_materials=my_materials, my_gear=my_gear, peak_name=_peak_name(char),
                            realm_by_index=realm_by_index, consult_left=max(0, consult_left),
                            train_left=max(0, train_left), mentor_train_physique=MENTOR_TRAIN_PHYSIQUE)

@app.route('/mentor/propose/<int:target_id>', methods=['POST'])
@login_required
def mentor_propose(target_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['peak_id']:
        flash('尚未拜入一峰,无从拜师', 'error')
        return redirect(url_for('mentor_home'))
    existing = _mentor_row(char['id'])
    if existing and existing['status'] in ('active', 'pending'):
        flash('终身只能拜一位师父,除非师父身故,否则无法另投他师' if existing['status'] == 'active'
              else '已有拜师请求待对方回应,请耐心等候', 'error')
        return redirect(url_for('mentor_home'))
    target = q("SELECT * FROM characters WHERE id=?", (target_id,), one=True)
    peak = q("SELECT elder_id FROM peaks WHERE id=?", (char['peak_id'],), one=True)
    target_serves_peak = bool(target and peak and peak['elder_id'] == target['id'])
    if not target or (target['peak_id'] != char['peak_id'] and not target_serves_peak) or target['id'] == char['id']:
        flash('对方不是同峰师兄姐', 'error')
        return redirect(url_for('mentor_home'))
    if target['deceased'] or target['ascended']:
        flash('对方已不在,无法拜师', 'error')
        return redirect(url_for('mentor_home'))
    if target['is_npc']:
        zi = random.choice(MENTOR_ZI_POOL)
        if existing:
            run("UPDATE discipleships SET master_id=?, status='active', created_ts=? WHERE disciple_id=?",
                (target_id, now_ts(), char['id']))
        else:
            run("INSERT INTO discipleships (master_id,disciple_id,status,created_ts) VALUES (?,?,'active',?)",
                (target_id, char['id'], now_ts()))
        run("UPDATE characters SET zi=? WHERE id=?", (zi, char['id']))
        _grant_material(char['id'], MENTOR_NPC_GIFT_MATERIAL, MENTOR_NPC_GIFT_QTY)
        flash(f"{target['name']}欣然应允,赐字「{zi}」,并赠{MATERIAL_LABELS[MENTOR_NPC_GIFT_MATERIAL]}×{MENTOR_NPC_GIFT_QTY}为礼", 'ok')
        log_chronicle(f"{char['name']}({title_for(char['join_seq'], char['gender'])})拜入{target['name']}门下,得赐字「{zi}」")
    else:
        if existing:
            run("UPDATE discipleships SET master_id=?, status='pending', created_ts=? WHERE disciple_id=?",
                (target_id, now_ts(), char['id']))
        else:
            run("INSERT INTO discipleships (master_id,disciple_id,status,created_ts) VALUES (?,?,'pending',?)",
                (target_id, char['id'], now_ts()))
        send_system_mail(target_id, '拜师请求',
                          f"{char['name']}欲拜入你门下为徒,请前往「拜师」页面回应(接受时需赐字、赠一份礼物)。",
                          from_label='宗门·执事堂')
        flash(f"已向{target['name']}递交拜师帖,静候回应", 'ok')
    return redirect(url_for('mentor_home'))

@app.route('/mentor/accept/<int:disciple_id>', methods=['POST'])
@login_required
def mentor_accept(disciple_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    row = q("SELECT * FROM discipleships WHERE disciple_id=? AND master_id=? AND status='pending'",
            (disciple_id, char['id']), one=True)
    if not row:
        flash('没有这条待处理的拜师请求', 'error')
        return redirect(url_for('mentor_home'))
    zi = request.form.get('zi', '').strip()[:6]
    if not zi:
        flash('请先赐字,再收下这位徒弟', 'error')
        return redirect(url_for('mentor_home'))
    gift_kind = request.form.get('gift_kind')
    gift_key = request.form.get('gift_key', '').strip()
    if gift_kind not in ('material', 'gear') or not gift_key:
        flash('请选一件礼物送给徒弟', 'error')
        return redirect(url_for('mentor_home'))
    try:
        gift_qty = int(request.form.get('gift_qty', '1'))
    except (TypeError, ValueError):
        gift_qty = 0
    if gift_qty <= 0:
        flash('赠礼数量必须至少为1', 'error')
        return redirect(url_for('mentor_home'))
    if gift_kind == 'material':
        if not _consume_materials(char['id'], {gift_key: gift_qty}):
            flash('材料不足或状态已变化', 'error')
            return redirect(url_for('mentor_home'))
        _grant_material(disciple_id, gift_key, gift_qty)
        gift_label = MATERIAL_LABELS.get(gift_key, gift_key)
    else:
        if not _inventory_consume(char['id'], 'gear', gift_qty, gift_key):
            flash('装备不足或状态已变化', 'error')
            return redirect(url_for('mentor_home'))
        _inventory_grant(disciple_id, 'gear', gift_qty, gift_key)
        gift_label = _market_item_label('gear', gift_key)
    run("UPDATE discipleships SET status='active' WHERE id=?", (row['id'],))
    run("UPDATE characters SET zi=? WHERE id=?", (zi, disciple_id))
    disciple = q("SELECT name, join_seq, gender FROM characters WHERE id=?", (disciple_id,), one=True)
    send_system_mail(disciple_id, '拜师有成', f"{char['name']}收你为徒,赐字「{zi}」,并赠{gift_label}×{gift_qty}。",
                      from_label='宗门·执事堂')
    log_chronicle(f"{disciple['name']}({title_for(disciple['join_seq'], disciple['gender'])})"
                  f"拜入{char['name']}门下,得赐字「{zi}」")
    flash(f"已收{disciple['name']}为徒,赐字「{zi}」,赠{gift_label}×{gift_qty}", 'ok')
    return redirect(url_for('mentor_home'))

@app.route('/mentor/decline/<int:disciple_id>', methods=['POST'])
@login_required
def mentor_decline(disciple_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    cur = run("UPDATE discipleships SET status='ended' WHERE disciple_id=? AND master_id=? AND status='pending'",
              (disciple_id, char['id']))
    if cur.rowcount:
        disciple = q("SELECT name FROM characters WHERE id=?", (disciple_id,), one=True)
        send_system_mail(disciple_id, '拜师被拒', f"{char['name']}婉拒了你的拜师之意。", from_label='宗门·执事堂')
        flash('已婉拒', 'ok')
    else:
        flash('没有这条待处理的拜师请求', 'error')
    return redirect(url_for('mentor_home'))

MENTOR_CONSULT_DAILY_LIMIT = 1
MENTOR_CONSULT_REPUTATION = 8
MENTOR_CONSULT_EXP_MULT = 3  # 一次请教约抵三次普通打坐的收益,每日限一次,不替代日常修炼
MENTOR_TRAIN_DAILY_LIMIT = 1
MENTOR_TRAIN_PHYSIQUE = 5

@app.route('/mentor/train/<int:disciple_id>', methods=['POST'])
@login_required
def mentor_train(disciple_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    disciple = q("""SELECT c.* FROM discipleships d
                      JOIN characters c ON c.id=d.disciple_id
                      WHERE d.master_id=? AND d.disciple_id=? AND d.status='active'
                        AND c.deceased=0 AND c.ascended=0""", (char['id'], disciple_id), one=True)
    if not disciple:
        flash('对方不是你当前可以带领训练的徒弟', 'error')
        return redirect(url_for('mentor_home'))
    if get_daily_counter(char['id'], 'mentor_train') >= MENTOR_TRAIN_DAILY_LIMIT:
        flash('今日已带徒弟训练过了,明日再来', 'error')
        return redirect(url_for('mentor_home'))
    bump_daily_counter(char['id'], 'mentor_train')
    run("UPDATE characters SET physique=physique+? WHERE id IN (?,?)",
        (MENTOR_TRAIN_PHYSIQUE, char['id'], disciple_id))
    flash(f"你与{disciple['name']}一同操练,师徒二人体魄各+{MENTOR_TRAIN_PHYSIQUE}", 'ok')
    return redirect(url_for('mentor_home'))

@app.route('/mentor/consult', methods=['POST'])
@login_required
def mentor_consult():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    my_row = _mentor_row(char['id'])
    if not my_row or my_row['status'] != 'active':
        flash('尚未拜得师父,无从请教', 'error')
        return redirect(url_for('mentor_home'))
    if get_daily_counter(char['id'], 'mentor_consult') >= MENTOR_CONSULT_DAILY_LIMIT:
        flash('今日已向师父请教过了,明日再来', 'error')
        return redirect(url_for('mentor_home'))
    bump_daily_counter(char['id'], 'mentor_consult')
    realm_mult = BASE_EXP_REALM_MULT.get(realm_major_idx(char['realm_idx']), 1)
    exp_gain = round(CULTIVATE_BASE_EXP_AVG * realm_mult * MENTOR_CONSULT_EXP_MULT)
    apply_reward(char['id'], {'exp': exp_gain, 'reputation': MENTOR_CONSULT_REPUTATION})
    master = q("SELECT name FROM characters WHERE id=?", (my_row['master_id'],), one=True)
    flash(f"向{master['name']}请教一番,修为+{exp_gain},声望+{MENTOR_CONSULT_REPUTATION}", 'ok')
    return redirect(url_for('mentor_home'))

# ── 羁绊:义结金兰(可多个)/ 道侣(唯一),双方同意方可缔结,缔结后打坐修为互相加成 ────────

def bond_exp_bonus_pct(char_id):
    rows = q("SELECT bond_type,affinity FROM bonds WHERE status='active' AND (char_a_id=? OR char_b_id=?)",
             (char_id, char_id))
    pct = 0
    sworn_bonus = sum(BOND_TYPES['sworn']['exp_bonus_pct'] + _bond_stage(r['affinity'])['index'] // 2
                       for r in rows if r['bond_type'] == 'sworn')
    pct += min(sworn_bonus, BOND_TYPES['sworn']['cap_pct'])
    companion = next((r for r in rows if r['bond_type'] == 'companion'), None)
    if companion:
        pct += BOND_TYPES['companion']['exp_bonus_pct'] + _bond_stage(companion['affinity'])['index']
    return pct

def _bond_stage(affinity):
    affinity = max(0, min(100, affinity or 0))
    index = max(i for i, (threshold, _) in enumerate(BOND_STAGE_THRESHOLDS) if affinity >= threshold)
    threshold, label = BOND_STAGE_THRESHOLDS[index]
    next_threshold = BOND_STAGE_THRESHOLDS[index + 1][0] if index + 1 < len(BOND_STAGE_THRESHOLDS) else None
    return {'index': index, 'label': label, 'threshold': threshold, 'next_threshold': next_threshold,
            'progress_pct': affinity if next_threshold else 100}

def get_bonds(char_id):
    rows = q("""SELECT bonds.*, (CASE WHEN char_a_id=? THEN char_b_id ELSE char_a_id END) partner_id
                FROM bonds WHERE status='active' AND (char_a_id=? OR char_b_id=?)""",
             (char_id, char_id, char_id))
    result = []
    for r in rows:
        partner = q("SELECT id,name,join_seq,gender,ascended,deceased FROM characters WHERE id=?",
                    (r['partner_id'],), one=True)
        if partner:
            affinity = r['affinity'] or 0
            stage = _bond_stage(affinity)
            cultivation_bonus = (BOND_TYPES[r['bond_type']]['exp_bonus_pct'] +
                                  (stage['index'] if r['bond_type'] == 'companion' else stage['index'] // 2))
            memories = [dict(m) for m in q("""SELECT bi.memory_text,bi.created_ts,c.name actor_name
                FROM bond_interactions bi JOIN characters c ON c.id=bi.actor_id
                WHERE bi.bond_id=? ORDER BY bi.created_ts DESC,bi.id DESC LIMIT 4""", (r['id'],))]
            interacted_today = bool(q("SELECT 1 FROM bond_interactions WHERE bond_id=? AND actor_id=? AND day=?",
                                      (r['id'], char_id, today_str()), one=True))
            actions = []
            for key, action in BOND_INTERACTIONS.items():
                reward_parts = []
                if action['mind_gain']:
                    reward_parts.append(f"双方心境+{action['mind_gain']}")
                actions.append(dict(action, key=key, reward_desc='、'.join(reward_parts)))
            result.append({'id': r['id'], 'bond_type': r['bond_type'], 'partner': dict(partner),
                           'affinity': affinity, 'stage': stage, 'memories': memories,
                           'cultivation_bonus': cultivation_bonus,
                           'interacted_today': interacted_today, 'actions': actions,
                           'accepted_ts': r['accepted_ts'] or r['created_ts']})
    return result

def get_pending_bonds(char_id):
    sent = q("""SELECT bonds.*, characters.name partner_name FROM bonds
                JOIN characters ON characters.id = bonds.char_b_id
                WHERE bonds.char_a_id=? AND bonds.status='pending'""", (char_id,))
    received = q("""SELECT bonds.*, characters.name partner_name FROM bonds
                    JOIN characters ON characters.id = bonds.char_a_id
                    WHERE bonds.char_b_id=? AND bonds.status='pending'""", (char_id,))
    return sent, received

def _gift_roll(char_id, gift_type, source_key):
    gift_def = GIFT_TYPES[gift_type]
    char = q("SELECT name,forger_level,alchemist_level FROM characters WHERE id=?", (char_id,), one=True)
    craft_bonus = min(10, ((char['forger_level'] or 1) + (char['alchemist_level'] or 1)) // 2) if source_key == 'crafted' else 0
    roll = random.randint(1, 100) + craft_bonus + (6 if source_key == 'mystic' else 0)
    rarity_key = 'unique' if roll >= 99 else 'rare' if roll >= 88 else 'fine' if roll >= 58 else 'plain'
    preferred_trait = {'mystic': 'mystic', 'travel': 'weathered', 'xiaxia': 'heroic'}.get(source_key)
    trait_key = preferred_trait if preferred_trait and random.random() < 0.65 else random.choice(list(GIFT_TRAITS))
    base_name = random.choice(gift_def['names'])
    prefix = {'plain': '', 'fine': '精制·', 'rare': '灵韵·', 'unique': '天成·'}[rarity_key]
    source_label = GIFT_SOURCE_LABELS[source_key]
    origin = (f"{char['name']}亲手制作，工序中意外生出「{GIFT_TRAITS[trait_key]['label']}」之特质。"
              if source_key == 'crafted' else
              f"{char['name']}于{source_label}途中偶然获得，其上留有「{GIFT_TRAITS[trait_key]['label']}」。")
    cur = run("""INSERT INTO bond_gifts
        (maker_id,owner_id,gift_type,gift_name,rarity_key,trait_key,source_key,origin_text,status,created_ts)
        VALUES(?,?,?,?,?,?,?,?, 'inventory',?)""",
        (char_id, char_id, gift_type, prefix + base_name, rarity_key, trait_key, source_key, origin, now_ts()))
    return {'id': cur.lastrowid, 'name': prefix + base_name, 'rarity_key': rarity_key,
            'rarity_label': GIFT_RARITIES[rarity_key]['label'], 'trait_label': GIFT_TRAITS[trait_key]['label']}

def _maybe_find_gift(char_id, source_key):
    if random.random() >= GIFT_FIND_CHANCES[source_key]:
        return None
    gift_type = random.choice(list(GIFT_TYPES))
    return _gift_roll(char_id, gift_type, source_key)

def _gift_view(row):
    gift = dict(row)
    gift['type_label'] = GIFT_TYPES[gift['gift_type']]['label']
    gift['rarity'] = GIFT_RARITIES[gift['rarity_key']]
    gift['trait'] = GIFT_TRAITS[gift['trait_key']]
    gift['source_label'] = GIFT_SOURCE_LABELS[gift['source_key']]
    gift['equip_slot'] = GIFT_EQUIP_SLOTS.get(gift['gift_type'])
    return gift

@app.route('/bag')
@login_required
def bag_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    materials = [dict(r, label=MATERIAL_LABELS.get(r['material_key'], r['material_key']))
                 for r in q("SELECT * FROM character_materials WHERE char_id=? AND qty>0 ORDER BY material_key", (char['id'],))]
    pills = [dict(r, label=ALCHEMY_RECIPES_BY_KEY.get(r['recipe_key'], {}).get('label', r['recipe_key']))
             for r in q("SELECT * FROM character_pills WHERE char_id=? AND qty>0 ORDER BY recipe_key", (char['id'],))]
    gear = [dict(r, label=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('label', r['item_key']),
                 slot=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('slot'))
            for r in q("SELECT * FROM character_equipment WHERE char_id=? AND qty>0 ORDER BY item_key", (char['id'],))]
    artifacts = [dict(r, label=_market_item_label('artifact', r['form'], r['element_key'], r['rarity_key']))
                 for r in q("SELECT * FROM character_artifacts WHERE char_id=? AND qty>0", (char['id'],))]
    gifts = [_gift_view(r) for r in q("SELECT * FROM bond_gifts WHERE owner_id=? AND status IN ('inventory','cherished') ORDER BY created_ts DESC", (char['id'],))]
    shard_qtys = {tk: _material_qty(char['id'], pastlife_talent_shard_key(tk)) for tk in TALENTS}
    return render_template('bag.html', char=char, materials=materials, pills=pills, gear=gear,
                           artifacts=artifacts, gifts=gifts,
                           shard_qtys=shard_qtys, shard_cost=PASTLIFE_TALENT_SHARD_COST, TALENTS=TALENTS,
                           talent_awaken_realm_name=REALMS[TALENT_AWAKEN_REALM]['name'],
                           PASTLIFE_TALENT_REINFORCE_COST=PASTLIFE_TALENT_REINFORCE_COST,
                           PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS=PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS,
                           PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS=PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS)

@app.route('/bonds/gifts')
@login_required
def gifts_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    owned = [_gift_view(r) for r in q("SELECT * FROM bond_gifts WHERE owner_id=? AND status='inventory' ORDER BY created_ts DESC", (char['id'],))]
    incoming = [_gift_view(r) for r in q("""SELECT g.*,c.name maker_name FROM bond_gifts g
        LEFT JOIN characters c ON c.id=g.maker_id WHERE g.recipient_id=? AND g.status='pending' ORDER BY g.gifted_ts DESC""", (char['id'],))]
    outgoing = [_gift_view(r) for r in q("""SELECT g.*,c.name recipient_name FROM bond_gifts g
        LEFT JOIN characters c ON c.id=g.recipient_id WHERE g.maker_id=? AND g.status='pending' ORDER BY g.gifted_ts DESC""", (char['id'],))]
    cherished = [_gift_view(r) for r in q("""SELECT g.*,c.name maker_name FROM bond_gifts g
        LEFT JOIN characters c ON c.id=g.maker_id WHERE g.owner_id=? AND g.status='cherished' ORDER BY g.responded_ts DESC""", (char['id'],))]
    equipped_ids = {char['equipped_tassel_gift_id'], char['equipped_jade_gift_id']} - {None}
    for gift in owned + cherished:
        gift['is_equipped'] = gift['id'] in equipped_ids
    bonds = get_bonds(char['id'])
    materials = {key: _material_qty(char['id'], key) for key in MATERIAL_TIERS}
    gift_types = {key: dict(info, can_craft=_has_materials(char['id'], info['cost']))
                  for key, info in GIFT_TYPES.items()}
    return render_template('gifts.html', char=char, owned=owned, incoming=incoming, outgoing=outgoing, cherished=cherished,
                           bonds=bonds, gift_types=gift_types, materials=materials, material_labels=MATERIAL_LABELS,
                           BOND_TYPES=BOND_TYPES)

@app.route('/bonds/gifts/craft/<gift_type>', methods=['POST'])
@login_required
def gift_craft(gift_type):
    char = me_character()
    gift_def = GIFT_TYPES.get(gift_type)
    if not char or not gift_def:
        flash('不知该如何制作此物', 'error')
        return redirect(url_for('gifts_home'))
    if not _has_materials(char['id'], gift_def['cost']):
        flash('制作材料不足', 'error')
        return redirect(url_for('gifts_home'))
    _consume_materials(char['id'], gift_def['cost'])
    gift = _gift_roll(char['id'], gift_type, 'crafted')
    flash(f"亲手制成「{gift['rarity_label']}·{gift['name']}」，意外得到特质「{gift['trait_label']}」", 'ok')
    return redirect(url_for('gifts_home'))

@app.route('/bonds/gifts/send/<int:gift_id>', methods=['POST'])
@login_required
def gift_send(gift_id):
    char = me_character()
    gift = q("SELECT * FROM bond_gifts WHERE id=? AND owner_id=? AND status='inventory'", (gift_id, char['id']), one=True) if char else None
    bond_id = request.form.get('bond_id', type=int)
    bond = q("SELECT * FROM bonds WHERE id=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
             (bond_id, char['id'], char['id']), one=True) if char and bond_id else None
    if not gift or not bond:
        flash('礼物或羁绊已失效', 'error')
        return redirect(url_for('gifts_home'))
    if char['equipped_tassel_gift_id'] == gift_id or char['equipped_jade_gift_id'] == gift_id:
        flash('这件正佩戴在身上,先卸下再送人', 'error')
        return redirect(url_for('gifts_home'))
    recipient_id = bond['char_b_id'] if bond['char_a_id'] == char['id'] else bond['char_a_id']
    day_start = int(time.mktime(date.today().timetuple()))
    if q("SELECT 1 FROM bond_gifts WHERE bond_id=? AND maker_id=? AND gifted_ts>=?",
         (bond_id, char['id'], day_start), one=True):
        flash('今日已向此人赠过礼，心意贵在不滥', 'error')
        return redirect(url_for('gifts_home'))
    message = request.form.get('message', '').strip()[:80]
    run("UPDATE bond_gifts SET recipient_id=?,bond_id=?,message=?,status='pending',gifted_ts=? WHERE id=?",
        (recipient_id, bond_id, message, now_ts(), gift_id))
    send_system_mail(recipient_id, '有人赠你一件礼物',
                     f"{char['name']}送来一件独一无二的礼物，正在同心鉴·赠礼阁中等你亲自查看。", from_label='宗门·赠礼阁')
    flash('礼物已送出，静候对方回应', 'ok')
    return redirect(url_for('gifts_home'))

@app.route('/bonds/gifts/equip/<int:gift_id>', methods=['POST'])
@login_required
def gift_equip(gift_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    gift = q("SELECT * FROM bond_gifts WHERE id=? AND owner_id=? AND status IN ('inventory','cherished')",
             (gift_id, char['id']), one=True)
    if not gift:
        flash('这件礼物不在你手上', 'error')
        return redirect(url_for('gifts_home'))
    slot = GIFT_EQUIP_SLOTS.get(gift['gift_type'])
    if not slot:
        flash('这件礼物无法佩戴', 'error')
        return redirect(url_for('gifts_home'))
    run(f"UPDATE characters SET equipped_{slot}_gift_id=? WHERE id=?", (gift_id, char['id']))
    flash(f"已佩戴「{gift['gift_name']}」", 'ok')
    return redirect(url_for('gifts_home'))

@app.route('/bonds/gifts/unequip/<slot>', methods=['POST'])
@login_required
def gift_unequip(slot):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if slot not in ('tassel', 'jade'):
        flash('槽位不存在', 'error')
        return redirect(url_for('gifts_home'))
    run(f"UPDATE characters SET equipped_{slot}_gift_id=NULL WHERE id=?", (char['id'],))
    flash('已卸下', 'ok')
    return redirect(url_for('gifts_home'))

@app.route('/bonds/gifts/recall/<int:gift_id>', methods=['POST'])
@login_required
def gift_recall(gift_id):
    char = me_character()
    cur = run("UPDATE bond_gifts SET recipient_id=NULL,status='inventory',responded_ts=? WHERE id=? AND maker_id=? AND status='pending'",
              (now_ts(), gift_id, char['id'])) if char else None
    flash('礼物已收回行囊' if cur and cur.rowcount else '这份礼物已被处理', 'ok' if cur and cur.rowcount else 'error')
    return redirect(url_for('gifts_home'))

@app.route('/bonds/gifts/respond/<int:gift_id>/<response>', methods=['POST'])
@login_required
def gift_respond(gift_id, response):
    char = me_character()
    gift = q("SELECT * FROM bond_gifts WHERE id=? AND recipient_id=? AND status='pending'", (gift_id, char['id']), one=True) if char else None
    if not gift or response not in ('accept', 'decline'):
        flash('这份礼物已被处理', 'error')
        return redirect(url_for('gifts_home'))
    if response == 'decline':
        run("UPDATE bond_gifts SET recipient_id=NULL,status='inventory',responded_ts=? WHERE id=?", (now_ts(), gift_id))
        flash('你婉言谢绝了这份心意，礼物已原样退回', 'ok')
        return redirect(url_for('gifts_home'))
    active_bond = q("SELECT 1 FROM bonds WHERE id=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
                    (gift['bond_id'], char['id'], char['id']), one=True)
    if not active_bond:
        run("UPDATE bond_gifts SET recipient_id=NULL,status='inventory',responded_ts=? WHERE id=?", (now_ts(), gift_id))
        flash('这段羁绊已经结束，礼物已原样退回', 'error')
        return redirect(url_for('gifts_home'))
    gain = (GIFT_TYPES[gift['gift_type']]['base_affinity'] + GIFT_RARITIES[gift['rarity_key']]['affinity_bonus'] +
            GIFT_TRAITS[gift['trait_key']]['affinity_bonus'])
    giver = q("SELECT name FROM characters WHERE id=?", (gift['maker_id'],), one=True)
    memory = f"{giver['name']}将「{gift['gift_name']}」赠予{char['name']}，{char['name']}郑重收入珍藏。"
    run("UPDATE bond_gifts SET owner_id=?,status='cherished',responded_ts=? WHERE id=?", (char['id'], now_ts(), gift_id))
    run("UPDATE bonds SET affinity=MIN(100,affinity+?) WHERE id=? AND status='active'", (gain, gift['bond_id']))
    run("""INSERT INTO bond_interactions(bond_id,actor_id,action_key,day,memory_text,affinity_gain,created_ts)
        VALUES(?,?,?,?,?,?,?)""", (gift['bond_id'], gift['maker_id'], 'gift', f'gift-{gift_id}', memory, gain, now_ts()))
    flash(f"你收下「{gift['gift_name']}」并纳入珍藏，双方默契+{gain}", 'ok')
    return redirect(url_for('gifts_home'))

@app.route('/bond/interact/<int:bond_id>/<action_key>', methods=['POST'])
@login_required
def bond_interact(bond_id, action_key):
    char = me_character()
    action = BOND_INTERACTIONS.get(action_key)
    if not char or not action:
        flash('无法进行这次互动', 'error')
        return redirect(url_for('home'))
    if in_retreat(char):
        flash('你正在闭关中,心无旁骛,出关后再来', 'error')
        return redirect(url_for('retreat_home'))
    if in_labor(char):
        flash('你正在外出打工,分身乏术,出工后再来', 'error')
        return redirect(url_for('labor_home'))
    bond = q("SELECT * FROM bonds WHERE id=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
             (bond_id, char['id'], char['id']), one=True)
    if not bond:
        flash('这段羁绊已不存在', 'error')
        return redirect(url_for('home'))
    if q("SELECT 1 FROM bond_interactions WHERE bond_id=? AND actor_id=? AND day=?",
         (bond_id, char['id'], today_str()), one=True):
        flash('今日已与此人相伴过，留些话明日再说', 'error')
        return redirect(url_for('home'))
    if char['stamina'] < action['stamina_cost']:
        flash(f"体力不足，{action['label']}需要{action['stamina_cost']}点体力", 'error')
        return redirect(url_for('home'))
    partner_id = bond['char_b_id'] if bond['char_a_id'] == char['id'] else bond['char_a_id']
    partner = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0", (partner_id,), one=True)
    if not partner:
        flash('对方此刻不在宗门中', 'error')
        return redirect(url_for('home'))
    memory = random.choice(action['flavors']).format(actor=char['name'], partner=partner['name'])
    before_stage = _bond_stage(bond['affinity'] or 0)
    db = get_db()
    try:
        db.execute("UPDATE characters SET stamina=MAX(0,stamina-?), mind_state=MIN(100,mind_state+?) WHERE id=?",
                   (action['stamina_cost'], action['mind_gain'], char['id']))
        db.execute("UPDATE characters SET mind_state=MIN(100,mind_state+?) WHERE id=?",
                   (action['mind_gain'], partner_id))
        db.execute("UPDATE bonds SET affinity=MIN(100,affinity+?) WHERE id=?", (action['affinity_gain'], bond_id))
        db.execute("""INSERT INTO bond_interactions
            (bond_id,actor_id,action_key,day,memory_text,affinity_gain,created_ts) VALUES(?,?,?,?,?,?,?)""",
                   (bond_id, char['id'], action_key, today_str(), memory, action['affinity_gain'], now_ts()))
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash('今日已与此人相伴过', 'error')
        return redirect(url_for('home'))
    after_affinity = min(100, (bond['affinity'] or 0) + action['affinity_gain'])
    after_stage = _bond_stage(after_affinity)
    reward = []
    if action['mind_gain']:
        reward.append(f"双方心境+{action['mind_gain']}")
    msg = f"{memory} 默契+{action['affinity_gain']}"
    if reward:
        msg += '，' + '、'.join(reward)
    if after_stage['index'] > before_stage['index']:
        msg += f"——你们的关系已至「{after_stage['label']}」"
        send_system_mail(partner_id, '羁绊有所感',
                         f"{char['name']}与你的默契已至「{after_stage['label']}」。{memory}", from_label='宗门·同心鉴')
    else:
        send_system_mail(partner_id, f"{char['name']}来找你{action['label']}了",
                         f"{memory} 默契+{action['affinity_gain']}", from_label='宗门·同心鉴')
    flash(msg, 'ok')
    return redirect(url_for('home') + '#bonds')

@app.route('/bond/invite/<int:char_id>/<bond_type>', methods=['POST'])
@login_required
def bond_invite(char_id, bond_type):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if bond_type not in BOND_TYPES:
        flash('未知的羁绊类型', 'error')
        return redirect(url_for('roster'))
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0", (char_id,), one=True)
    if not target or target['id'] == char['id']:
        flash('对方不在宗门中', 'error')
        return redirect(url_for('character_detail', char_id=char_id))
    existing = q("""SELECT 1 FROM bonds WHERE bond_type=? AND status IN ('pending','active')
                     AND ((char_a_id=? AND char_b_id=?) OR (char_a_id=? AND char_b_id=?))""",
                 (bond_type, char['id'], char_id, char_id, char['id']), one=True)
    if existing:
        flash('你们之间已有相同类型的羁绊或邀请', 'error')
        return redirect(url_for('character_detail', char_id=char_id))
    if not BOND_TYPES[bond_type]['stackable']:
        mine = q("SELECT 1 FROM bonds WHERE bond_type=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
                 (bond_type, char['id'], char['id']), one=True)
        theirs = q("SELECT 1 FROM bonds WHERE bond_type=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
                   (bond_type, char_id, char_id), one=True)
        if mine or theirs:
            flash(f"{BOND_TYPES[bond_type]['label']}唯一,已有一位,无法再缔结", 'error')
            return redirect(url_for('character_detail', char_id=char_id))
    run("INSERT INTO bonds (char_a_id,char_b_id,bond_type,status,created_ts) VALUES (?,?,?,'pending',?)",
        (char['id'], char_id, bond_type, now_ts()))
    if bond_type == 'companion':
        send_system_mail(char_id, '道侣之约',
                          f"{char['name']}向你递上道侣之约,愿此后同修共渡、生死相随,前往静室查看回应。")
    else:
        send_system_mail(char_id, f"{BOND_TYPES[bond_type]['label']}邀约",
                          f"{char['name']}向你发出{BOND_TYPES[bond_type]['label']}的邀约,前往静室查看并回应。")
    flash('邀约已送出,静候回应', 'ok')
    return redirect(url_for('character_detail', char_id=char_id))

@app.route('/bond/accept/<int:bond_id>', methods=['POST'])
@login_required
def bond_accept(bond_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    bond = q("SELECT * FROM bonds WHERE id=? AND char_b_id=? AND status='pending'", (bond_id, char['id']), one=True)
    if not bond:
        flash('该邀约已失效', 'error')
        return redirect(url_for('home'))
    bt = BOND_TYPES[bond['bond_type']]
    if not bt['stackable']:
        conflict = q("SELECT 1 FROM bonds WHERE bond_type=? AND status='active' AND (char_a_id=? OR char_b_id=? OR char_a_id=? OR char_b_id=?)",
                     (bond['bond_type'], char['id'], char['id'], bond['char_a_id'], bond['char_a_id']), one=True)
        if conflict:
            flash(f"{bt['label']}唯一,一方已有归属,邀约作废", 'error')
            run("DELETE FROM bonds WHERE id=?", (bond_id,))
            return redirect(url_for('home'))
    accepted_ts = now_ts()
    run("UPDATE bonds SET status='active', accepted_ts=?, affinity=MAX(affinity,5) WHERE id=?", (accepted_ts, bond_id))
    partner = q("SELECT * FROM characters WHERE id=?", (bond['char_a_id'],), one=True)
    bond_memory = (f"{partner['name']}与{char['name']}于宗门见证下结为{bt['label']}，"
                   f"从此道途上多了一位可并肩之人。")
    run("""INSERT OR IGNORE INTO bond_interactions
        (bond_id,actor_id,action_key,day,memory_text,affinity_gain,created_ts) VALUES(?,?,? ,?,?,?,?)""",
        (bond_id, char['id'], 'formed', f'formed-{bond_id}', bond_memory, 5, accepted_ts))
    if bond['bond_type'] == 'companion':
        send_system_mail(partner['id'], '道侣缔结',
                          f"{char['name']}接受了你的道侣之约,自此结为道侣,愿此后灵犀相印,同渡万劫。")
        run("UPDATE characters SET mind_state=MAX(0,MIN(100,mind_state+?)) WHERE id IN (?,?)",
            (COMPANION_BOND_MIND_GIFT, char['id'], partner['id']))
        title_a = title_for(partner['join_seq'], partner['gender'])
        title_b = title_for(char['join_seq'], char['gender'])
        for c in q("SELECT id FROM characters"):
            send_system_mail(c['id'], '喜结道侣',
                              f"{partner['name']}({title_a})与{char['name']}({title_b})喜结道侣之好,自此携手同修,宗门同贺!",
                              from_label='宗门公告')
    else:
        send_system_mail(partner['id'], f"{bt['label']}缔结", f"{char['name']}接受了你的{bt['label']}之约,自此结为{bt['label']}。")
    log_chronicle(f"{partner['name']}({title_for(partner['join_seq'], partner['gender'])})"
                   f"与{char['name']}({title_for(char['join_seq'], char['gender'])}){bt['label']}",
                  major=bond['bond_type'] == 'companion')
    flash(f"已与{partner['name']}结为{bt['label']}", 'ok')
    return redirect(url_for('home'))

@app.route('/bond/decline/<int:bond_id>', methods=['POST'])
@login_required
def bond_decline(bond_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    run("DELETE FROM bonds WHERE id=? AND (char_a_id=? OR char_b_id=?) AND status='pending'",
        (bond_id, char['id'], char['id']))
    flash('已处理该邀约', 'ok')
    return redirect(url_for('home'))

@app.route('/bond/dissolve/<int:bond_id>', methods=['POST'])
@login_required
def bond_dissolve(bond_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    bond = q("SELECT * FROM bonds WHERE id=? AND (char_a_id=? OR char_b_id=?) AND status='active'",
             (bond_id, char['id'], char['id']), one=True)
    if not bond:
        flash('该羁绊不存在', 'error')
        return redirect(url_for('home'))
    partner_id = bond['char_b_id'] if bond['char_a_id'] == char['id'] else bond['char_a_id']
    partner = q("SELECT * FROM characters WHERE id=?", (partner_id,), one=True)
    run("UPDATE bonds SET status='dissolved' WHERE id=?", (bond_id,))
    bt = BOND_TYPES[bond['bond_type']]
    if partner:
        if bond['bond_type'] == 'companion':
            send_system_mail(partner['id'], '道侣和离', f"{char['name']}提出和离,道侣之约就此解除,往后各自珍重。")
            log_chronicle(f"{char['name']}与{partner['name']}和离,道侣之约解除", major=True)
        else:
            send_system_mail(partner['id'], f"{bt['label']}解除", f"{char['name']}解除了与你的{bt['label']}之约。")
            log_chronicle(f"{char['name']}与{partner['name']}解除{bt['label']}")
    flash('已解除该羁绊', 'ok')
    return redirect(url_for('home'))

# ── 子嗣:求子(参考突破仪式的保底模式)→ 被动成长+教养 → 陨落风险 → 结亲代代相传 ──────────
# 父母字段多态(角色/子嗣/散修NPC),_resolve_owner_chars 递归解析出"谁能为这个子嗣做主",
# 这样孙辈及以后的婚配/求子天然由双方的真人祖辈共同操办,不需要给子嗣自己开账号。

def _resolve_owner_chars(kind, entity_id):
    if kind == 'character':
        return {entity_id}
    if kind == 'offspring':
        off = q("SELECT parent_a_kind,parent_a_id,parent_b_kind,parent_b_id FROM offspring WHERE id=?",
                (entity_id,), one=True)
        if not off:
            return set()
        owners = _resolve_owner_chars(off['parent_a_kind'], off['parent_a_id'])
        if off['parent_b_kind'] != 'npc' and off['parent_b_id']:
            owners |= _resolve_owner_chars(off['parent_b_kind'], off['parent_b_id'])
        return owners
    return set()

def _party_field(kind, entity_id, field):
    if kind == 'character':
        row = q(f"SELECT {field} FROM characters WHERE id=?", (entity_id,), one=True)
    elif kind == 'offspring':
        row = q(f"SELECT {field} FROM offspring WHERE id=?", (entity_id,), one=True)
    else:
        return None
    return row[field] if row else None

def _offspring_stage_notice(off, new_realm):
    """境界推进跨越了成长阶段边界时,发一次带性格/爱好 flavor 的里程碑通知——不是每次教养都发。"""
    old_stage = offspring_stage(off['realm_idx'])
    new_stage = offspring_stage(new_realm)
    if new_stage == old_stage:
        return
    p_label = OFFSPRING_PERSONALITIES.get(off['personality_key'], {}).get('label', '')
    h_label = OFFSPRING_HOBBIES.get(off['hobby_key'], {}).get('label', '')
    text = offspring_stage_flavor(off['name'], new_stage, p_label, h_label)
    for owner_id in _resolve_owner_chars('offspring', off['id']):
        send_system_mail(owner_id, f"{off['name']}·{new_stage}", text)

def sync_offspring_growth(off):
    off = dict(off)
    if not off['alive'] or off['realm_idx'] >= OFFSPRING_REALM_CAP_IDX:
        return off
    if off['frail_warned_ts']:
        # 体弱期间成长暂停,不会自动恶化;只推进时钟基准,避免痊愈后突然结算一大段"补涨"
        run("UPDATE offspring SET last_growth_ts=? WHERE id=?", (now_ts(), off['id']))
        off['last_growth_ts'] = now_ts()
        return off
    elapsed_hours = (now_ts() - off['last_growth_ts']) // 3600
    if elapsed_hours <= 0:
        return off
    gained = int(elapsed_hours * OFFSPRING_PASSIVE_EXP_PER_HOUR)
    new_exp = off['exp'] + gained
    new_realm = off['realm_idx']
    while new_realm < OFFSPRING_REALM_CAP_IDX and new_exp >= REALMS[new_realm + 1]['exp']:
        new_realm += 1
    if new_realm != off['realm_idx']:
        _offspring_stage_notice(off, new_realm)
    run("UPDATE offspring SET exp=?, realm_idx=?, last_growth_ts=? WHERE id=?",
        (new_exp, new_realm, now_ts(), off['id']))
    off['exp'] = new_exp; off['realm_idx'] = new_realm; off['last_growth_ts'] = now_ts()
    return off

def _companion_conceive_context(char):
    bond = q("SELECT * FROM bonds WHERE bond_type='companion' AND status='active' AND (char_a_id=? OR char_b_id=?)",
             (char['id'], char['id']), one=True)
    if not bond:
        return None
    partner_id = bond['char_b_id'] if bond['char_a_id'] == char['id'] else bond['char_a_id']
    return {'parent_a_kind': 'character', 'parent_a_id': char['id'],
            'parent_b_kind': 'character', 'parent_b_id': partner_id, 'parent_b_npc_name': None,
            'owners': {char['id'], partner_id}, 'generation': 1,
            'bond_row': bond, 'bond_created_ts': bond['accepted_ts'] or bond['created_ts']}

def _offspring_couple_context(off_id):
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off:
        return None
    if off['spouse_offspring_id']:
        spouse = q("SELECT * FROM offspring WHERE id=?", (off['spouse_offspring_id'],), one=True)
        if not spouse:
            return None
        owners = _resolve_owner_chars('offspring', off['id']) | _resolve_owner_chars('offspring', spouse['id'])
        return {'parent_a_kind': 'offspring', 'parent_a_id': off['id'],
                'parent_b_kind': 'offspring', 'parent_b_id': spouse['id'], 'parent_b_npc_name': None,
                'owners': owners, 'generation': max(off['generation'], spouse['generation']) + 1,
                'a_row': off}
    if off['spouse_npc_name']:
        owners = _resolve_owner_chars('offspring', off['id'])
        return {'parent_a_kind': 'offspring', 'parent_a_id': off['id'],
                'parent_b_kind': 'npc', 'parent_b_id': None, 'parent_b_npc_name': off['spouse_npc_name'],
                'owners': owners, 'generation': off['generation'] + 1,
                'a_row': off}
    return None

def _find_growing_offspring(ctx):
    return q("""SELECT * FROM offspring WHERE alive=1 AND realm_idx<?
                AND parent_a_kind=? AND parent_a_id=? AND parent_b_kind=? AND parent_b_id IS ?""",
             (OFFSPRING_MARRY_REALM_IDX, ctx['parent_a_kind'], ctx['parent_a_id'],
              ctx['parent_b_kind'], ctx['parent_b_id']), one=True)

def _offspring_family_tree(mine):
    """按代分组(1代子嗣/2代孙辈...)并搭出简易家族树:每代挂在其对应上一代父母名下,
    方便页面分层展示,而不是所有子孙混在一条平铺列表里。"""
    generations = {}
    for o in mine:
        generations.setdefault(o['generation'], []).append(o)
    tree = []
    for o in generations.get(1, []):
        children = [c for c in generations.get(2, [])
                    if (c['parent_a_kind'] == 'offspring' and c['parent_a_id'] == o['id'])
                    or (c['parent_b_kind'] == 'offspring' and c['parent_b_id'] == o['id'])]
        tree.append({'parent': o, 'children': children})
    return generations, tree

def _my_offspring(char_id):
    result = list(q("""SELECT * FROM offspring WHERE (parent_a_kind='character' AND parent_a_id=?)
                        OR (parent_b_kind='character' AND parent_b_id=?)""", (char_id, char_id)))
    seen = {o['id'] for o in result}
    frontier = list(seen)
    while frontier:
        placeholders = ','.join('?' * len(frontier))
        children = q(f"""SELECT * FROM offspring WHERE (parent_a_kind='offspring' AND parent_a_id IN ({placeholders}))
                          OR (parent_b_kind='offspring' AND parent_b_id IN ({placeholders}))""",
                     tuple(frontier) * 2)
        frontier = []
        for c in children:
            if c['id'] not in seen:
                seen.add(c['id']); result.append(c); frontier.append(c['id'])
    return result

@app.route('/offspring')
@login_required
def offspring_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = sync_stamina(char)
    mine = [sync_offspring_growth(o) for o in _my_offspring(char['id'])]
    mine_ids = {o['id'] for o in mine} or {-1}

    companion_ctx = _companion_conceive_context(char)
    companion = None
    if companion_ctx:
        bond = companion_ctx['bond_row']
        elapsed_days = (now_ts() - companion_ctx['bond_created_ts']) // 86400
        streak = bond['conceive_fail_streak']
        companion = {
            'ctx': companion_ctx,
            'wait_ok': elapsed_days >= OFFSPRING_COMPANION_MIN_DAYS,
            'wait_days_left': max(0, OFFSPRING_COMPANION_MIN_DAYS - elapsed_days),
            'growing': _find_growing_offspring(companion_ctx),
            'streak': streak,
            'chance_pct': round(min(0.95, OFFSPRING_CONCEIVE_BASE_CHANCE +
                                 min(streak, OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK) *
                                 (OFFSPRING_CONCEIVE_PITY_INCREMENT_PCT / 100)) * 100),
            'guaranteed': streak >= OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK,
            'cooldown_left': max(0, OFFSPRING_CONCEIVE_COOLDOWN_SECONDS - (now_ts() - bond['conceive_last_ts'])),
            'gen_capped': companion_ctx['generation'] > OFFSPRING_MAX_GENERATION,
        }

    married_couples = []
    for o in mine:
        if o['alive'] and (o['spouse_offspring_id'] or o['spouse_npc_name']):
            ctx = _offspring_couple_context(o['id'])
            if not ctx:
                continue
            streak = o['conceive_fail_streak']
            married_couples.append({
                'off': o, 'ctx': ctx,
                'spouse_name': _party_field(ctx['parent_b_kind'], ctx['parent_b_id'], 'name') or ctx['parent_b_npc_name'],
                'growing': _find_growing_offspring(ctx),
                'streak': streak,
                'chance_pct': round(min(0.95, OFFSPRING_CONCEIVE_BASE_CHANCE +
                                     min(streak, OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK) *
                                     (OFFSPRING_CONCEIVE_PITY_INCREMENT_PCT / 100)) * 100),
                'guaranteed': streak >= OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK,
                'cooldown_left': max(0, OFFSPRING_CONCEIVE_COOLDOWN_SECONDS - (now_ts() - o['conceive_last_ts'])),
                'gen_capped': ctx['generation'] > OFFSPRING_MAX_GENERATION,
            })

    candidates = q("""SELECT * FROM offspring WHERE alive=1 AND realm_idx>=?
                       AND spouse_offspring_id IS NULL AND spouse_npc_name IS NULL""",
                   (OFFSPRING_MARRY_REALM_IDX,))
    candidates = [c for c in candidates if c['id'] not in mine_ids]

    placeholders = ','.join('?' * len(mine_ids))
    pending_received = q(f"""SELECT p.*, oa.name from_name, ob.name to_name FROM offspring_proposals p
                             JOIN offspring oa ON oa.id=p.from_offspring_id
                             JOIN offspring ob ON ob.id=p.to_offspring_id
                             WHERE p.status='pending' AND p.to_offspring_id IN ({placeholders})""",
                         tuple(mine_ids))
    pending_sent = q(f"""SELECT p.*, ob.name to_name FROM offspring_proposals p
                          JOIN offspring ob ON ob.id=p.to_offspring_id
                          WHERE p.status='pending' AND p.from_offspring_id IN ({placeholders})""",
                      tuple(mine_ids))

    for o in mine:
        if not o.get('archetype'):
            o['archetype'] = offspring_archetype(o['personality_key'], o['hobby_key'])
            o['life_event'] = o.get('life_event') or roll_offspring_life_event()
            run("UPDATE offspring SET archetype=?, life_event=? WHERE id=?",
                (o['archetype'], o['life_event'], o['id']))
        o['stage'] = offspring_stage(o['realm_idx'])
        o['realm_name'] = REALMS[o['realm_idx']]['name']
        o['marriageable'] = o['realm_idx'] >= OFFSPRING_MARRY_REALM_IDX
        o['married'] = bool(o['spouse_offspring_id'] or o['spouse_npc_name'])
        o['spouse_name'] = (_party_field('offspring', o['spouse_offspring_id'], 'name')
                             if o['spouse_offspring_id'] else o['spouse_npc_name'])
        o['manyue_revealed'] = o['manyue_status'] == 'done'
        if o['manyue_revealed']:
            o['personality_label'] = OFFSPRING_PERSONALITIES.get(o['personality_key'], {}).get('label', '?')
            o['hobby_label'] = OFFSPRING_HOBBIES.get(o['hobby_key'], {}).get('label', '?')
        else:
            o['personality_label'] = o['hobby_label'] = o['archetype'] = None
        if o['frail_warned_ts']:
            o['heal_late'] = (now_ts() - o['frail_warned_ts']) > OFFSPRING_FRAIL_GRACE_HOURS * 3600
            o['heal_cost'] = OFFSPRING_HEAL_CONTRIBUTION_COST * (
                OFFSPRING_FRAIL_HEAL_LATE_MULT if o['heal_late'] else 1)
        if o['married'] and o['married_ts']:
            o['revoke_left'] = max(0, MARRIAGE_REVOKE_WINDOW_SECONDS - (now_ts() - o['married_ts']))

    generations, family_tree = _offspring_family_tree(mine)

    return render_template('offspring.html', char=char, mine=mine, companion=companion,
                            married_couples=married_couples, candidates=candidates,
                            pending_received=pending_received, pending_sent=pending_sent,
                            generations=generations, family_tree=family_tree,
                            REALMS=REALMS, offspring_stage=offspring_stage,
                            OFFSPRING_PERSONALITIES=OFFSPRING_PERSONALITIES, OFFSPRING_HOBBIES=OFFSPRING_HOBBIES,
                            OFFSPRING_MARRY_REALM_IDX=OFFSPRING_MARRY_REALM_IDX,
                            OFFSPRING_REALM_CAP_IDX=OFFSPRING_REALM_CAP_IDX,
                            OFFSPRING_TEACH_STAMINA_COST=OFFSPRING_TEACH_STAMINA_COST,
                            OFFSPRING_TEACH_DAILY_LIMIT=OFFSPRING_TEACH_DAILY_LIMIT,
                            OFFSPRING_CONCEIVE_STAMINA_COST=OFFSPRING_CONCEIVE_STAMINA_COST,
                            OFFSPRING_CONCEIVE_CONTRIBUTION_COST=OFFSPRING_CONCEIVE_CONTRIBUTION_COST,
                            OFFSPRING_HEAL_CONTRIBUTION_COST=OFFSPRING_HEAL_CONTRIBUTION_COST,
                            OFFSPRING_COMPANION_MIN_DAYS=OFFSPRING_COMPANION_MIN_DAYS,
                            OFFSPRING_PER_COUPLE_LIFETIME_CAP=OFFSPRING_PER_COUPLE_LIFETIME_CAP,
                            conceive_daily_cap=OFFSPRING_CONCEIVE_DAILY_CAP,
                            conceive_daily_left=max(0, OFFSPRING_CONCEIVE_DAILY_CAP
                                                     - get_daily_counter(char['id'], 'offspring_conceive')),
                            OFFSPRING_RENAME_COST=OFFSPRING_RENAME_COST)

@app.route('/offspring/conceive', methods=['POST'])
@login_required
def offspring_conceive():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    via = request.form.get('via_offspring_id', type=int)

    if via:
        ctx = _offspring_couple_context(via)
        if not ctx or char['id'] not in ctx['owners']:
            flash('无权为此操办此事', 'error')
            return redirect(url_for('offspring_home'))
        streak_row = ctx['a_row']
        streak, last_ts, row_id = streak_row['conceive_fail_streak'], streak_row['conceive_last_ts'], streak_row['id']
        table = 'offspring'
    else:
        ctx = _companion_conceive_context(char)
        if not ctx:
            flash('尚未结为道侣,无从求子', 'error')
            return redirect(url_for('offspring_home'))
        if now_ts() - ctx['bond_created_ts'] < OFFSPRING_COMPANION_MIN_DAYS * 86400:
            flash(f"结为道侣未满{OFFSPRING_COMPANION_MIN_DAYS}日,尚不到求子之时", 'error')
            return redirect(url_for('offspring_home'))
        bond = ctx['bond_row']
        streak, last_ts, row_id = bond['conceive_fail_streak'], bond['conceive_last_ts'], bond['id']
        table = 'bonds'

    if ctx['generation'] > OFFSPRING_MAX_GENERATION:
        flash('血脉传承已至圆满,不必再求', 'error')
        return redirect(url_for('offspring_home'))
    if _find_growing_offspring(ctx):
        flash('膝下已有子嗣尚未长成,且宽限些时日', 'error')
        return redirect(url_for('offspring_home'))
    total_children = q("""SELECT COUNT(*) c FROM offspring
                           WHERE parent_a_kind=? AND parent_a_id=? AND parent_b_kind=? AND parent_b_id IS ?""",
                       (ctx['parent_a_kind'], ctx['parent_a_id'], ctx['parent_b_kind'], ctx['parent_b_id']),
                       one=True)['c']
    if total_children >= OFFSPRING_PER_COUPLE_LIFETIME_CAP:
        flash(f'膝下已有{total_children}位子嗣,门庭已然兴旺,不必再添', 'error')
        return redirect(url_for('offspring_home'))
    if now_ts() - last_ts < OFFSPRING_CONCEIVE_COOLDOWN_SECONDS:
        flash('刚试过,尚需时日调养', 'error')
        return redirect(url_for('offspring_home'))
    if get_daily_counter(char['id'], 'offspring_conceive') >= OFFSPRING_CONCEIVE_DAILY_CAP:
        flash(f"今日已求子{OFFSPRING_CONCEIVE_DAILY_CAP}次,明日再来", 'error')
        return redirect(url_for('offspring_home'))
    if char['stamina'] < OFFSPRING_CONCEIVE_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('offspring_home'))
    cur = run("""UPDATE characters SET stamina=stamina-?, contribution=contribution-? WHERE id=?
                 AND stamina>=? AND contribution>=?""",
              (OFFSPRING_CONCEIVE_STAMINA_COST, OFFSPRING_CONCEIVE_CONTRIBUTION_COST, char['id'],
               OFFSPRING_CONCEIVE_STAMINA_COST, OFFSPRING_CONCEIVE_CONTRIBUTION_COST))
    if cur.rowcount == 0:
        flash('体力或贡献不足', 'error')
        return redirect(url_for('offspring_home'))
    run(f"UPDATE {table} SET conceive_last_ts=? WHERE id=?", (now_ts(), row_id))
    bump_daily_counter(char['id'], 'offspring_conceive')

    chance = OFFSPRING_CONCEIVE_BASE_CHANCE + min(streak, OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK) * (
        OFFSPRING_CONCEIVE_PITY_INCREMENT_PCT / 100)
    guaranteed = streak >= OFFSPRING_CONCEIVE_PITY_GUARANTEE_STREAK
    success = guaranteed or random.random() <= min(0.95, chance)

    if not success:
        run(f"UPDATE {table} SET conceive_fail_streak=conceive_fail_streak+1 WHERE id=?", (row_id,))
        flash('此次未能求得,且宽心静养,来日再试', 'error')
        return redirect(url_for('offspring_home'))

    run(f"UPDATE {table} SET conceive_fail_streak=0 WHERE id=?", (row_id,))
    root_a = _party_field(ctx['parent_a_kind'], ctx['parent_a_id'], 'spirit_root')
    root_b = _party_field(ctx['parent_b_kind'], ctx['parent_b_id'], 'spirit_root')
    talent_a = _party_field(ctx['parent_a_kind'], ctx['parent_a_id'], 'talent_key')
    talent_b = _party_field(ctx['parent_b_kind'], ctx['parent_b_id'], 'talent_key')
    new_root = roll_offspring_spirit_root(root_a, root_b)
    new_talent = roll_offspring_talent(talent_a, talent_b)
    new_personality = roll_offspring_personality()
    new_hobby = roll_offspring_hobby()
    new_archetype = offspring_archetype(new_personality, new_hobby)
    new_life_event = roll_offspring_life_event()
    gender = random.choice(['m', 'f'])
    parent_a_name = _party_field(ctx['parent_a_kind'], ctx['parent_a_id'], 'name')
    custom_name = request.form.get('name', '').strip()[:12]
    name = custom_name or f"{parent_a_name}之{'子' if gender == 'm' else '女'}"

    cur = run("""INSERT INTO offspring (name,gender,generation,parent_a_kind,parent_a_id,parent_b_kind,parent_b_id,
                    parent_b_npc_name,realm_idx,exp,spirit_root,talent_key,personality_key,hobby_key,
                    archetype,life_event,alive,born_ts,last_growth_ts,created_ts)
                 VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?,?,?,?,1,?,?,?)""",
        (name, gender, ctx['generation'], ctx['parent_a_kind'], ctx['parent_a_id'],
         ctx['parent_b_kind'], ctx['parent_b_id'], ctx.get('parent_b_npc_name'),
         new_root, new_talent, new_personality, new_hobby, new_archetype, new_life_event,
         now_ts(), now_ts(), now_ts()))

    for owner_id in ctx['owners']:
        send_system_mail(owner_id, '喜得麟儿',
                          f"{name}呱呱坠地,自此膝下承欢,好生教养。襁褓中的性子爱好尚看不真切,"
                          "不如办一场满月酒,请全宗同门来贺,借抓周之机,也好探探这孩子的秉性。")
    log_chronicle(f"{name}降世", major=True)
    flash(f"求子有成!{name}降世", 'ok')
    return redirect(url_for('offspring_home'))

# ── 满月酒:父母自动到场领福利、全宗广发请柬,来宾花灵石入场+投一件贺礼进抓周池,
# 一天后惰性结算(访问页面时触发),随机抓中一份贺礼公布于众,顺带揭晓孩子性子爱好 ──────────

def _manyue_roll_reward(char_id):
    """随机结算一份来宾福利;accessory档不当场落地,留给来宾自己去饰品堆里挑。"""
    kind = random.choices(list(MANYUE_REWARD_WEIGHTS.keys()), weights=list(MANYUE_REWARD_WEIGHTS.values()), k=1)[0]
    if kind == 'physique':
        amount = random.randint(*MANYUE_PHYSIQUE_GAIN_RANGE)
        run("UPDATE characters SET physique=physique+? WHERE id=?", (amount, char_id))
        return kind, {'amount': amount}, True
    if kind == 'material':
        mk = random.choices(list(MANYUE_MATERIAL_TIER_WEIGHTS.keys()),
                             weights=list(MANYUE_MATERIAL_TIER_WEIGHTS.values()), k=1)[0]
        qty = random.randint(2, 4)
        _grant_material(char_id, mk, qty)
        return kind, {'key': mk, 'qty': qty}, True
    return kind, None, False

def manyue_tick():
    """后台定时扫描:满月酒时限一到就自动揭晓,不用等家长或来宾恰好点进详情页才触发。"""
    for off in q("SELECT id FROM offspring WHERE manyue_status='active'"):
        _resolve_manyue_if_due(off['id'])

def _resolve_manyue_if_due(off_id):
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or off['manyue_status'] != 'active':
        return
    if now_ts() - off['manyue_started_ts'] < MANYUE_DURATION_SECONDS:
        return
    pool = q("SELECT * FROM manyue_pool WHERE offspring_id=?", (off_id,))
    p_label = OFFSPRING_PERSONALITIES.get(off['personality_key'], {}).get('label', '?')
    h_label = OFFSPRING_HOBBIES.get(off['hobby_key'], {}).get('label', '?')
    if pool:
        picked = random.choice(pool)
        item = ZHUAZHOU_ITEMS[picked['item_key']]
        guest = q("SELECT name FROM characters WHERE id=?", (picked['guest_char_id'],), one=True)
        guest_name = guest['name'] if guest else '有缘人'
        run("UPDATE offspring SET manyue_status='done', manyue_result_item_key=?, manyue_result_guest_id=? WHERE id=?",
            (picked['item_key'], picked['guest_char_id'], off_id))
        msg = (f"{off['name']}满月抓周,稚嫩小手一把抓住了{guest_name}带来的「{item['label']}」——{item['prediction']}"
               f" 借这场满月酒,同门也算摸清了这孩子的性子:{p_label},平日里最喜{h_label}。")
    else:
        run("UPDATE offspring SET manyue_status='done' WHERE id=?", (off_id,))
        msg = (f"{off['name']}的满月酒散场了,可惜抓周池里空空如也,没能抓中什么彩头。"
               f"不过借这场宴席,同门也算摸清了这孩子的性子:{p_label},平日里最喜{h_label}。")
    # 不用 url_for:这个函数现在也会被后台定时任务(manyue_tick)在没有请求上下文时调用,
    # url_for 在那种场合会直接报错,拼一个跟路由定义一致的相对路径字符串效果等价且更稳妥。
    link_url = f'/offspring/{off_id}/manyue'
    for c in q("SELECT id FROM characters"):
        send_system_mail(c['id'], '满月抓周·揭晓', msg, from_label='宗门·同心鉴', link_url=link_url)
    log_chronicle(msg, major=True)

@app.route('/offspring/<int:off_id>/manyue/host', methods=['POST'])
@login_required
def offspring_manyue_host(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    owners = _resolve_owner_chars('offspring', off_id)
    if char['id'] not in owners:
        flash('无权为此子嗣办满月酒', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off:
        flash('子嗣不存在', 'error')
        return redirect(url_for('offspring_home'))
    if off['manyue_status'] is not None:
        flash('这孩子的满月酒已经办过了', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE offspring SET manyue_status='active', manyue_started_ts=? WHERE id=?", (now_ts(), off_id))
    link_url = url_for('offspring_manyue', off_id=off_id)
    # 子嗣最多繁衍到第2代(见 OFFSPRING_MAX_GENERATION),owners 解析到的真实角色对1代子嗣是父母,
    # 对2代孙辈则是祖辈——称谓跟着代数走,别一律喊"父母";孙辈还要点出其父母是谁,免得看着糊涂。
    kin_label = '父母' if off['generation'] == 1 else '祖辈长辈'
    parent_note = ''
    if off['generation'] > 1:
        parent_a_name = _party_field(off['parent_a_kind'], off['parent_a_id'], 'name')
        parent_b_name = (off['parent_b_npc_name'] if off['parent_b_kind'] == 'npc'
                          else _party_field(off['parent_b_kind'], off['parent_b_id'], 'name'))
        parents = '、'.join(n for n in (parent_a_name, parent_b_name) if n)
        if parents:
            parent_note = f"(其父母是{parents})"
    for owner_id in owners:
        item_key = random.choice(list(ZHUAZHOU_ITEMS.keys()))
        reward_kind, reward_detail, claimed = _manyue_roll_reward(owner_id)
        run("""INSERT OR IGNORE INTO manyue_pool (offspring_id,guest_char_id,item_key,reward_kind,reward_detail,claimed,created_ts)
               VALUES (?,?,?,?,?,?,?)""",
            (off_id, owner_id, item_key, reward_kind,
             json.dumps(reward_detail) if reward_detail else None, int(claimed), now_ts()))
        send_system_mail(owner_id, '满月酒·请柬',
                          f"{off['name']}的满月酒已经办起来了,你身为孩子的{kin_label}{parent_note},自然是座上宾,"
                          f"已代为奉上一份「{ZHUAZHOU_ITEMS[item_key]['label']}」入抓周池,无需破费。"
                          "一天后揭晓抓周结果,记得去满月酒页面看看有没有福利要领。",
                          from_label='宗门·同心鉴', link_url=link_url)
    others = q("SELECT id FROM characters WHERE id NOT IN ({})".format(','.join('?' * len(owners))), tuple(owners))
    for r in others:
        send_system_mail(r['id'], '满月酒·请柬',
                          f"{off['name']}的满月酒开席了,花{MANYUE_ENTRY_LINGSHI_COST}灵石即可赴宴,"
                          "还可带一件贺礼投入抓周池,来宾皆有薄礼相送,一天后揭晓抓周结果。",
                          from_label='宗门·同心鉴', link_url=link_url)
    log_chronicle(f"{off['name']}办起满月酒,广邀全宗同门", major=True)
    flash('满月酒已办起来,请柬发往全宗,一天后见分晓', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/manyue')
@login_required
def offspring_manyue(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or off['manyue_status'] is None:
        flash('这孩子还没办过满月酒', 'error')
        return redirect(url_for('offspring_home'))
    _resolve_manyue_if_due(off_id)
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    my_pool_row = q("SELECT * FROM manyue_pool WHERE offspring_id=? AND guest_char_id=?", (off_id, char['id']), one=True)
    if my_pool_row:
        my_pool_row = dict(my_pool_row)
        my_pool_row['reward_detail'] = json.loads(my_pool_row['reward_detail']) if my_pool_row['reward_detail'] else {}
    guests = q("""SELECT mp.*, c.name guest_name FROM manyue_pool mp
                  JOIN characters c ON c.id = mp.guest_char_id WHERE mp.offspring_id=? ORDER BY mp.created_ts""", (off_id,))
    time_left = max(0, MANYUE_DURATION_SECONDS - (now_ts() - (off['manyue_started_ts'] or 0)))
    result_item = ZHUAZHOU_ITEMS.get(off['manyue_result_item_key']) if off['manyue_result_item_key'] else None
    result_guest = q("SELECT name FROM characters WHERE id=?", (off['manyue_result_guest_id'],), one=True) \
        if off['manyue_result_guest_id'] else None
    return render_template('offspring_manyue.html', char=char, off=off, my_pool_row=my_pool_row, guests=guests,
                            time_left=time_left, result_item=result_item, result_guest=result_guest,
                            ZHUAZHOU_ITEMS=ZHUAZHOU_ITEMS, MANYUE_GIFT_ACCESSORIES=MANYUE_GIFT_ACCESSORIES,
                            entry_cost=MANYUE_ENTRY_LINGSHI_COST, MATERIAL_LABELS=MATERIAL_LABELS)

@app.route('/offspring/<int:off_id>/manyue/attend', methods=['POST'])
@login_required
def offspring_manyue_attend(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or off['manyue_status'] != 'active':
        flash('这场满月酒已经结束或尚未开办', 'error')
        return redirect(url_for('offspring_home'))
    if now_ts() - off['manyue_started_ts'] >= MANYUE_DURATION_SECONDS:
        flash('满月酒已经散场了', 'error')
        return redirect(url_for('offspring_manyue', off_id=off_id))
    if q("SELECT 1 FROM manyue_pool WHERE offspring_id=? AND guest_char_id=?", (off_id, char['id']), one=True):
        flash('你已经来过了', 'error')
        return redirect(url_for('offspring_manyue', off_id=off_id))
    item_key = request.form.get('item_key', '')
    if item_key not in ZHUAZHOU_ITEMS:
        flash('请选一件贺礼', 'error')
        return redirect(url_for('offspring_manyue', off_id=off_id))
    # 同一场满月酒里贺礼不许重样,免得抓周池被扎堆的热门礼物挤满,抓周结果失了随机的意思;
    # 撞了礼就随机换一件这场还没人带过的,选不出别的(礼物池被点尽)才允许重样。
    used_keys = {r['item_key'] for r in q("SELECT item_key FROM manyue_pool WHERE offspring_id=?", (off_id,))}
    swapped_from = None
    if item_key in used_keys:
        available = [k for k in ZHUAZHOU_ITEMS if k not in used_keys]
        if available:
            swapped_from = item_key
            item_key = random.choice(available)
    if not _spend(char['id'], 'lingshi', MANYUE_ENTRY_LINGSHI_COST):
        flash('灵石不足', 'error')
        return redirect(url_for('offspring_manyue', off_id=off_id))
    reward_kind, reward_detail, claimed = _manyue_roll_reward(char['id'])
    run("""INSERT INTO manyue_pool (offspring_id,guest_char_id,item_key,reward_kind,reward_detail,claimed,created_ts)
           VALUES (?,?,?,?,?,?,?)""",
        (off_id, char['id'], item_key, reward_kind,
         json.dumps(reward_detail) if reward_detail else None, int(claimed), now_ts()))
    bring_desc = (f"你选的「{ZHUAZHOU_ITEMS[swapped_from]['label']}」已被人带过,临时换成了「{ZHUAZHOU_ITEMS[item_key]['label']}」"
                  if swapped_from else f"带去了「{ZHUAZHOU_ITEMS[item_key]['label']}」")
    if reward_kind == 'accessory':
        flash(f"赴宴成功!{bring_desc},抽中了福袋里的饰品档,下面任选一件领取", 'ok')
    elif reward_kind == 'physique':
        flash(f"赴宴成功!{bring_desc},喝了杯满月酒暖身,体魄+{reward_detail['amount']}", 'ok')
    else:
        flash(f"赴宴成功!{bring_desc},"
              f"主人家回礼{MATERIAL_LABELS[reward_detail['key']]}×{reward_detail['qty']}", 'ok')
    return redirect(url_for('offspring_manyue', off_id=off_id))

@app.route('/offspring/manyue/claim/<int:pool_id>/<item_key>', methods=['POST'])
@login_required
def offspring_manyue_claim(pool_id, item_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    row = q("SELECT * FROM manyue_pool WHERE id=? AND guest_char_id=? AND reward_kind='accessory' AND claimed=0",
            (pool_id, char['id']), one=True)
    if not row:
        flash('没有可领取的福利', 'error')
        return redirect(url_for('offspring_home'))
    tpl = next((a for a in MANYUE_GIFT_ACCESSORIES if a['key'] == item_key), None)
    if not tpl:
        flash('礼物不存在', 'error')
        return redirect(url_for('offspring_manyue', off_id=row['offspring_id']))
    _inventory_grant(char['id'], 'gear', 1, item_key)
    run("UPDATE manyue_pool SET claimed=1, reward_detail=? WHERE id=?", (json.dumps({'key': item_key}), pool_id))
    flash(f"领取了「{tpl['label']}」", 'ok')
    return redirect(url_for('offspring_manyue', off_id=row['offspring_id']))

@app.route('/offspring/<int:off_id>/rename', methods=['POST'])
@login_required
def offspring_rename(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权为此子嗣改名', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off:
        flash('子嗣不存在', 'error')
        return redirect(url_for('offspring_home'))
    name = request.form.get('name', '').strip()
    if not (1 <= len(name) <= 12):
        flash('名字长度需在1-12位之间', 'error')
        return redirect(url_for('offspring_home'))
    pay_with = request.form.get('pay_with')
    if pay_with not in ('contribution', 'lingshi'):
        flash('请选择用贡献还是灵石支付', 'error')
        return redirect(url_for('offspring_home'))
    if not _spend(char['id'], pay_with, OFFSPRING_RENAME_COST):
        flash(f"{'贡献' if pay_with == 'contribution' else '灵石'}不足{OFFSPRING_RENAME_COST}", 'error')
        return redirect(url_for('offspring_home'))
    old_name = off['name']
    run("UPDATE offspring SET name=? WHERE id=?", (name, off_id))
    if name != old_name:
        log_chronicle(f"{old_name}更名为{name}")
    flash(f"已更名为{name}", 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/teach', methods=['POST'])
@login_required
def offspring_teach(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权教养此子嗣', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not off['alive']:
        flash('子嗣不存在', 'error')
        return redirect(url_for('offspring_home'))
    if off['frail_warned_ts']:
        flash(f"{off['name']}近来体弱,须先寻医或明确选择冒险教养,不宜照常教养", 'error')
        return redirect(url_for('offspring_home'))
    off = sync_offspring_growth(off)
    if off['realm_idx'] >= OFFSPRING_REALM_CAP_IDX:
        flash('此子境界已至封顶,不必再教', 'error')
        return redirect(url_for('offspring_home'))
    char = sync_stamina(char)
    if char['stamina'] < OFFSPRING_TEACH_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('offspring_home'))
    counter_key = f'offspring_teach_{off_id}'
    if get_daily_counter(char['id'], counter_key) >= OFFSPRING_TEACH_DAILY_LIMIT:
        flash('今日已教养多次,该歇息了', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (OFFSPRING_TEACH_STAMINA_COST, char['id']))
    bump_daily_counter(char['id'], counter_key)

    gained = random.randint(*OFFSPRING_TEACH_EXP_RANGE)
    new_exp = off['exp'] + gained
    new_realm = off['realm_idx']
    while new_realm < OFFSPRING_REALM_CAP_IDX and new_exp >= REALMS[new_realm + 1]['exp']:
        new_realm += 1
    if new_realm != off['realm_idx']:
        _offspring_stage_notice(off, new_realm)
    run("UPDATE offspring SET exp=?, realm_idx=? WHERE id=?", (new_exp, new_realm, off_id))
    msg = f"教养{off['name']},见长 +{gained}"
    if new_realm > off['realm_idx']:
        msg += f",已至{REALMS[new_realm]['name']}"

    owners = _resolve_owner_chars('offspring', off_id)
    if off['realm_idx'] <= OFFSPRING_FRAIL_REALM_MAX and random.random() < OFFSPRING_FRAIL_WARN_CHANCE:
        run("UPDATE offspring SET frail_warned_ts=? WHERE id=?", (now_ts(), off_id))
        msg += f",然{off['name']}近来体弱,恐生变故,速速寻医方可安心"
        for owner_id in owners:
            send_system_mail(owner_id, '子嗣体弱',
                              f"{off['name']}近来体弱,恐生变故——可寻医化解,或冒险教养以图速愈,静室定夺。")
    elif (off['realm_idx'] >= OFFSPRING_MARRY_REALM_IDX and not off['spouse_offspring_id']
          and not off['spouse_npc_name'] and not off['npc_proposal_name']
          and random.random() < OFFSPRING_NPC_MARRIAGE_ROLL_CHANCE):
        suitor = roll_npc_spouse_name()
        run("UPDATE offspring SET npc_proposal_name=? WHERE id=?", (suitor, off_id))
        msg += f",偶遇游方散修{suitor}求亲,静室查看回应"
        for owner_id in owners:
            send_system_mail(owner_id, '散修求亲', f"{off['name']}偶遇游方散修{suitor}求亲,是否应允,前往静室定夺。")

    flash(msg, 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/teach_risky', methods=['POST'])
@login_required
def offspring_teach_risky(off_id):
    """体弱期间的"冒险教养":唯一会真正判定夭折的入口,必须玩家明确点选,不会被普通教养误触发。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权为此子嗣操办', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not off['alive'] or not off['frail_warned_ts']:
        flash('此子并无需要冒险应对之事', 'error')
        return redirect(url_for('offspring_home'))
    char = sync_stamina(char)
    if char['stamina'] < OFFSPRING_TEACH_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (OFFSPRING_TEACH_STAMINA_COST, char['id']))

    owners = _resolve_owner_chars('offspring', off_id)
    if random.random() < OFFSPRING_FRAIL_DEATH_CHANCE:
        cur = run("UPDATE offspring SET alive=0, deceased_ts=? WHERE id=? AND alive=1", (now_ts(), off_id))
        if cur.rowcount == 0:
            flash('此事已有旁人处理', 'ok')
            return redirect(url_for('offspring_home'))
        for owner_id in owners:
            send_system_mail(owner_id, '子嗣夭亡', f"{off['name']}未能挺过此劫,不幸夭亡。", from_label='宗门·执事堂')
        log_chronicle(f"{off['name']}体弱夭亡", major=True)
        flash(f"{off['name']}未能挺过此劫,夭亡", 'error')
        return redirect(url_for('offspring_home'))

    gained = random.randint(*OFFSPRING_TEACH_EXP_RANGE)
    new_exp = off['exp'] + gained
    new_realm = off['realm_idx']
    while new_realm < OFFSPRING_REALM_CAP_IDX and new_exp >= REALMS[new_realm + 1]['exp']:
        new_realm += 1
    cur = run("UPDATE offspring SET exp=?, realm_idx=?, frail_warned_ts=NULL WHERE id=? AND frail_warned_ts IS NOT NULL",
              (new_exp, new_realm, off_id))
    if cur.rowcount == 0:
        flash('此事已有旁人处理', 'ok')
        return redirect(url_for('offspring_home'))
    if new_realm != off['realm_idx']:
        _offspring_stage_notice(off, new_realm)
    flash(f"{off['name']}挺过此劫,已然痊愈,见长 +{gained}", 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/heal', methods=['POST'])
@login_required
def offspring_heal(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权操办', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not off['frail_warned_ts']:
        flash('并无不适', 'error')
        return redirect(url_for('offspring_home'))
    late = (now_ts() - off['frail_warned_ts']) > OFFSPRING_FRAIL_GRACE_HOURS * 3600
    heal_cost = OFFSPRING_HEAL_CONTRIBUTION_COST * (OFFSPRING_FRAIL_HEAL_LATE_MULT if late else 1)
    spend_cur = run("UPDATE characters SET contribution=contribution-? WHERE id=? AND contribution>=?",
                     (heal_cost, char['id'], heal_cost))
    if spend_cur.rowcount == 0:
        flash('贡献不足', 'error')
        return redirect(url_for('offspring_home'))
    cur = run("UPDATE offspring SET frail_warned_ts=NULL WHERE id=? AND frail_warned_ts IS NOT NULL", (off_id,))
    if cur.rowcount == 0:
        run("UPDATE characters SET contribution=contribution+? WHERE id=?", (heal_cost, char['id']))
        flash('此事已有旁人处理,贡献已退还', 'ok')
        return redirect(url_for('offspring_home'))
    flash(f"寻医问药,{off['name']}已然痊愈" + (f"(逾宽限期,费{heal_cost})" if late else ''), 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/propose/<int:target_id>', methods=['POST'])
@login_required
def offspring_propose(off_id, target_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权为此子嗣操办', 'error')
        return redirect(url_for('offspring_home'))
    a = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    b = q("SELECT * FROM offspring WHERE id=?", (target_id,), one=True)
    if not a or not b or not a['alive'] or not b['alive'] or a['id'] == b['id']:
        flash('对象不存在', 'error')
        return redirect(url_for('offspring_home'))
    if a['realm_idx'] < OFFSPRING_MARRY_REALM_IDX or b['realm_idx'] < OFFSPRING_MARRY_REALM_IDX:
        flash('尚未至适婚之龄', 'error')
        return redirect(url_for('offspring_home'))
    if a['spouse_offspring_id'] or a['spouse_npc_name'] or b['spouse_offspring_id'] or b['spouse_npc_name']:
        flash('一方已有婚配', 'error')
        return redirect(url_for('offspring_home'))
    a_owners = _resolve_owner_chars('offspring', a['id'])
    b_owners = _resolve_owner_chars('offspring', b['id'])
    if a_owners & b_owners:
        flash('同源血脉,不可结亲', 'error')
        return redirect(url_for('offspring_home'))
    existing = q("""SELECT 1 FROM offspring_proposals WHERE status='pending'
                     AND ((from_offspring_id=? AND to_offspring_id=?) OR (from_offspring_id=? AND to_offspring_id=?))""",
                 (a['id'], b['id'], b['id'], a['id']), one=True)
    if existing:
        flash('提议已在等待回应', 'error')
        return redirect(url_for('offspring_home'))
    run("INSERT INTO offspring_proposals (from_offspring_id,to_offspring_id,from_char_id,status,created_ts) "
        "VALUES (?,?,?,'pending',?)", (a['id'], b['id'], char['id'], now_ts()))
    for owner_id in b_owners:
        send_system_mail(owner_id, '提亲', f"{a['name']}家托人向{b['name']}提亲,前往静室查看回应。")
    flash('提议已送出,静候回应', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/proposal/<int:proposal_id>/accept', methods=['POST'])
@login_required
def offspring_proposal_accept(proposal_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    prop = q("SELECT * FROM offspring_proposals WHERE id=? AND status='pending'", (proposal_id,), one=True)
    if not prop:
        flash('该提议已失效', 'error')
        return redirect(url_for('offspring_home'))
    b_owners = _resolve_owner_chars('offspring', prop['to_offspring_id'])
    if char['id'] not in b_owners:
        flash('无权回应', 'error')
        return redirect(url_for('offspring_home'))
    a = q("SELECT * FROM offspring WHERE id=?", (prop['from_offspring_id'],), one=True)
    b = q("SELECT * FROM offspring WHERE id=?", (prop['to_offspring_id'],), one=True)
    if (not a or not b or a['spouse_offspring_id'] or b['spouse_offspring_id']
            or a['spouse_npc_name'] or b['spouse_npc_name']):
        run("UPDATE offspring_proposals SET status='invalid' WHERE id=?", (proposal_id,))
        flash('一方已另有婚配,提议作废', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE offspring SET spouse_offspring_id=?, married_ts=? WHERE id=?", (b['id'], now_ts(), a['id']))
    run("UPDATE offspring SET spouse_offspring_id=?, married_ts=? WHERE id=?", (a['id'], now_ts(), b['id']))
    run("UPDATE offspring_proposals SET status='accepted', accepted_ts=? WHERE id=?", (now_ts(), proposal_id))
    run("""UPDATE offspring_proposals SET status='invalid' WHERE status='pending' AND id!=?
           AND (from_offspring_id IN (?,?) OR to_offspring_id IN (?,?))""",
        (proposal_id, a['id'], b['id'], a['id'], b['id']))
    all_owners = _resolve_owner_chars('offspring', a['id']) | _resolve_owner_chars('offspring', b['id'])
    revoke_hint = f"({MARRIAGE_REVOKE_WINDOW_SECONDS // 60}分钟内如有异议仍可撤回)"
    for owner_id in all_owners:
        send_system_mail(owner_id, '喜结良缘',
                          f"{a['name']}与{b['name']}结为伉俪,两家自此结为姻亲。{revoke_hint}", from_label='宗门公告')
    log_chronicle(f"{a['name']}与{b['name']}结为姻亲", major=True)
    flash('结亲已成', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/proposal/<int:proposal_id>/decline', methods=['POST'])
@login_required
def offspring_proposal_decline(proposal_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    prop = q("SELECT * FROM offspring_proposals WHERE id=? AND status='pending'", (proposal_id,), one=True)
    if prop:
        owners = (_resolve_owner_chars('offspring', prop['to_offspring_id'])
                  | _resolve_owner_chars('offspring', prop['from_offspring_id']))
        if char['id'] in owners:
            run("UPDATE offspring_proposals SET status='declined' WHERE id=?", (proposal_id,))
    flash('已回绝该提议', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/npc_marry/accept', methods=['POST'])
@login_required
def offspring_npc_marry_accept(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权操办', 'error')
        return redirect(url_for('offspring_home'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not off['npc_proposal_name'] or off['spouse_offspring_id'] or off['spouse_npc_name']:
        flash('并无此议', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE offspring SET spouse_npc_name=?, npc_proposal_name=NULL, married_ts=? WHERE id=?",
        (off['npc_proposal_name'], now_ts(), off_id))
    revoke_hint = f"({MARRIAGE_REVOKE_WINDOW_SECONDS // 60}分钟内如有异议仍可撤回)"
    for owner_id in _resolve_owner_chars('offspring', off_id):
        send_system_mail(owner_id, '喜结良缘', f"{off['name']}与游方之士{off['npc_proposal_name']}结为伉俪。{revoke_hint}")
    log_chronicle(f"{off['name']}与散修{off['npc_proposal_name']}结为连理", major=True)
    flash('已应允此门婚事', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/npc_marry/decline', methods=['POST'])
@login_required
def offspring_npc_marry_decline(off_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['id'] not in _resolve_owner_chars('offspring', off_id):
        flash('无权操办', 'error')
        return redirect(url_for('offspring_home'))
    run("UPDATE offspring SET npc_proposal_name=NULL WHERE id=?", (off_id,))
    flash('已回绝此门婚事', 'ok')
    return redirect(url_for('offspring_home'))

@app.route('/offspring/<int:off_id>/revoke_marriage', methods=['POST'])
@login_required
def offspring_revoke_marriage(off_id):
    """结亲后的短暂磋商期:任一方家长若不同意另一方家长擅自应允的婚事,可在窗口内撤回。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not (off['spouse_offspring_id'] or off['spouse_npc_name']) or not off['married_ts']:
        flash('并无可撤回的婚事', 'error')
        return redirect(url_for('offspring_home'))
    spouse_id = off['spouse_offspring_id']
    owners = _resolve_owner_chars('offspring', off_id) | (
        _resolve_owner_chars('offspring', spouse_id) if spouse_id else set())
    if char['id'] not in owners:
        flash('无权操办', 'error')
        return redirect(url_for('offspring_home'))
    if now_ts() - off['married_ts'] > MARRIAGE_REVOKE_WINDOW_SECONDS:
        flash('磋商期已过,婚事已定,不可再撤回', 'error')
        return redirect(url_for('offspring_home'))
    cur = run("UPDATE offspring SET spouse_offspring_id=NULL, spouse_npc_name=NULL, married_ts=NULL "
              "WHERE id=? AND married_ts=?", (off_id, off['married_ts']))
    if cur.rowcount == 0:
        flash('此事已有旁人处理', 'ok')
        return redirect(url_for('offspring_home'))
    spouse_name = off['spouse_npc_name']
    if spouse_id:
        run("UPDATE offspring SET spouse_offspring_id=NULL, married_ts=NULL WHERE id=?", (spouse_id,))
        spouse_name = _party_field('offspring', spouse_id, 'name')
    for owner_id in owners:
        send_system_mail(owner_id, '婚事撤回', f"{off['name']}与{spouse_name}的婚事在磋商期内被撤回,双方仍可另议良缘。")
    log_chronicle(f"{off['name']}与{spouse_name}的婚事被撤回")
    flash('已撤回此门婚事', 'ok')
    return redirect(url_for('offspring_home'))

# ── 私信:玩家互发,每日限额防刷屏 ────────────────────────────────────────────────

def send_player_mail(from_char, to_char_id, subject, body, attachment=None):
    run("INSERT INTO mail (char_id,from_char_id,from_label,subject,body,attachment_json,claimed,read,created_ts) "
        "VALUES (?,?,?,?,?,?,0,0,?)",
        (to_char_id, from_char['id'], from_char['name'], subject, body,
         json.dumps(attachment, ensure_ascii=False) if attachment else None, now_ts()))

@app.route('/mail/compose/<int:char_id>', methods=['GET', 'POST'])
@login_required
def mail_compose(char_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    target = q("SELECT * FROM characters WHERE id=? AND ascended=0 AND deceased=0", (char_id,), one=True)
    if not target:
        # 已飞升者只收得到在世至亲的信(见 _mortal_ascended_kin),不是随便什么人都能去信打扰
        candidate = q("SELECT * FROM characters WHERE id=? AND ascended=1", (char_id,), one=True)
        if candidate and any(r['id'] == candidate['id'] for r in _mortal_ascended_kin(char['id'])):
            target = candidate
    if not target or target['id'] == char['id']:
        flash('对方不在宗门中', 'error')
        return redirect(url_for('roster'))
    # 灵珠(合体渡劫·灵珠秘境专属材料)算绑定物品,跟宗门制式装备不许转赠他人一个口径
    materials_owned = {r['material_key']: r['qty'] for r in q(
        "SELECT material_key, qty FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))
        if r['material_key'] != 'lingzhu_bead'}
    # 宗门制式配发/唯一法宝(zone in unique/sect)算"绑定"物品,跟分解/温养一个口径,不许转赠他人
    equipment_owned = [dict(r, label=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('label', r['item_key']))
                       for r in q("SELECT item_key, qty FROM character_equipment WHERE char_id=? AND qty>0", (char['id'],))
                       if EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('zone') not in ('unique', 'sect')]

    def _render_form(subject, body):
        return render_template('mail_compose.html', char=char, target=target, subject=subject, body=body,
                                materials_owned=materials_owned, material_labels=MATERIAL_LABELS,
                                equipment_owned=equipment_owned)

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        attach_lingshi = max(0, request.form.get('attach_lingshi', type=int) or 0)
        attach_material_key = request.form.get('attach_material_key', '').strip()
        attach_material_qty = max(0, request.form.get('attach_material_qty', type=int) or 0)
        attach_equipment_key = request.form.get('attach_equipment_key', '').strip()
        attach_equipment_qty = max(0, request.form.get('attach_equipment_qty', type=int) or 0)
        if not (1 <= len(subject) <= 40):
            flash('标题长度需在 1-40 位之间', 'error')
            return _render_form(subject, body)
        if get_daily_counter(char['id'], 'player_mail') >= MAIL_DAILY_LIMIT:
            flash('今日发信次数已用完', 'error')
            return redirect(url_for('character_detail', char_id=char_id))
        if attach_material_key and (attach_material_key not in MATERIAL_LABELS or attach_material_key == 'lingzhu_bead'):
            attach_material_key = ''
            attach_material_qty = 0
        equip_tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(attach_equipment_key)
        if attach_equipment_key and (not equip_tpl or equip_tpl.get('zone') in ('unique', 'sect')):
            attach_equipment_key = ''
            attach_equipment_qty = 0
        attachment = {}
        if attach_lingshi > 0:
            if not _spend(char['id'], 'lingshi', attach_lingshi):
                flash('灵石不足,附不上这么多', 'error')
                return _render_form(subject, body)
            attachment['lingshi'] = attach_lingshi
        if attach_material_key and attach_material_qty > 0:
            if not _inventory_consume(char['id'], 'material', attach_material_qty, attach_material_key):
                if attach_lingshi > 0:
                    run("UPDATE characters SET lingshi=lingshi+? WHERE id=?", (attach_lingshi, char['id']))
                flash('这份材料你没有这么多', 'error')
                return _render_form(subject, body)
            attachment['materials'] = {attach_material_key: attach_material_qty}
        if attach_equipment_key and attach_equipment_qty > 0:
            if not _inventory_consume(char['id'], 'gear', attach_equipment_qty, attach_equipment_key):
                if attach_lingshi > 0:
                    run("UPDATE characters SET lingshi=lingshi+? WHERE id=?", (attach_lingshi, char['id']))
                if attachment.get('materials'):
                    for mk, mq in attachment['materials'].items():
                        _grant_material(char['id'], mk, mq)
                flash('这件装备你没有这么多', 'error')
                return _render_form(subject, body)
            attachment['equipment'] = {attach_equipment_key: attach_equipment_qty}
        if attachment:
            body = body + (f"\n\n随信附上:{_reward_desc(attachment)}" if body else f"随信附上:{_reward_desc(attachment)}")
        bump_daily_counter(char['id'], 'player_mail')
        send_player_mail(char, char_id, subject, body, attachment=attachment or None)
        flash(f"已寄出给{target['name']}的信", 'ok')
        return redirect(url_for('character_detail', char_id=char_id))
    return _render_form('', '')

# ── 灵宠:仅灵宠峰(紫霄峰)弟子可收养,身边最多8只(roster),超额先进临时驿站(holding)──
# 24小时不处理自动转灵兽峰(sanctuary,仅可查看)。出战(equipped_pet_id)只认roster里的那一只。

def _place_pet(char_id, pet_id):
    """新宠物到手(领养/买入/取消挂单退回)时决定去处:roster未满直接进roster,满了进holding等玩家处理。
    返回True=直接进roster,False=进了holding。"""
    roster_count = q("SELECT COUNT(*) c FROM character_pets WHERE char_id=? AND location='roster'",
                      (char_id,), one=True)['c']
    if roster_count < PET_ROSTER_CAP:
        run("UPDATE character_pets SET location='roster', holding_expires_ts=0 WHERE id=?", (pet_id,))
        return True
    run("UPDATE character_pets SET location='holding', holding_expires_ts=? WHERE id=?",
        (now_ts() + PET_HOLDING_HOURS * 3600, pet_id))
    return False

def _resolve_pet_holding_expiry(char_id):
    run("UPDATE character_pets SET location='sanctuary' WHERE char_id=? AND location='holding' AND holding_expires_ts<?",
        (char_id, now_ts()))

@app.route('/pet/adopt', methods=['POST'])
@login_required
def pet_adopt():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('pet'):
        flash('唯有灵宠峰弟子可收养灵宠', 'error')
        return redirect(url_for('home'))
    char = sync_stamina(char)
    if char['stamina'] < PET_ADOPT_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('pet_sanctuary'))
    if get_daily_counter(char['id'], 'pet_adopt') >= PET_ADOPT_DAILY_LIMIT:
        flash('今日已收养过灵宠,明日再来', 'error')
        return redirect(url_for('pet_sanctuary'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (PET_ADOPT_STAMINA_COST, char['id']))
    bump_daily_counter(char['id'], 'pet_adopt')
    name = request.form.get('name', '').strip()[:12] or None
    pet_key = roll_pet_type()
    appearance, personality, habit = roll_pet_identity()
    quality_label = PET_QUALITIES[pet_quality(pet_key)]['label']
    history = f"由{char['name']}在紫霄峰培育成{quality_label}灵宠"
    cur = run("""INSERT INTO character_pets
        (char_id,pet_key,pet_name,appearance,personality,habit,breeder_name,history,level,exp,bound_ts,location)
        VALUES (?,?,?,?,?,?,?,?,1,0,?,'holding')""",
        (char['id'], pet_key, name, appearance, personality, habit, char['name'], history, now_ts()))
    placed_in_roster = _place_pet(char['id'], cur.lastrowid)
    if not char['equipped_pet_id'] and placed_in_roster:
        run("UPDATE characters SET equipped_pet_id=? WHERE id=?", (cur.lastrowid, char['id']))
    msg = f"培育有成!得{quality_label}·{appearance}{PET_TYPES[pet_key]['label']}" + (f",取名{name}" if name else '')
    if not placed_in_roster:
        msg += f"。身边灵宠已满{PET_ROSTER_CAP}只,新宠暂居驿站,{PET_HOLDING_HOURS}小时内请去灵兽峰安排,否则将自动移入灵兽峰"
    flash(msg, 'ok')
    return redirect(url_for('pet_sanctuary'))

@app.route('/pet/train/<int:pet_id>', methods=['POST'])
@login_required
def pet_train(pet_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    pet = q("SELECT * FROM character_pets WHERE id=? AND char_id=?", (pet_id, char['id']), one=True)
    if not pet:
        flash('灵宠不存在', 'error')
        return redirect(url_for('pet_sanctuary'))
    if pet['location'] != 'roster':
        flash('只有身边的灵宠才能训养,寄养/驿站中的灵宠先召回身边', 'error')
        return redirect(url_for('pet_sanctuary'))
    char = sync_stamina(char)
    max_level = pet_max_level(pet['pet_key'])
    if pet['level'] >= max_level:
        flash('灵宠已臻大成,无需再训', 'error')
        return redirect(url_for('pet_sanctuary'))
    if char['stamina'] < PET_TRAIN_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('pet_sanctuary'))
    if get_daily_counter(char['id'], 'pet_train') >= PET_TRAIN_DAILY_LIMIT:
        flash('今日已训养多次,灵宠该歇息了', 'error')
        return redirect(url_for('pet_sanctuary'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (PET_TRAIN_STAMINA_COST, char['id']))
    bump_daily_counter(char['id'], 'pet_train')
    gained = random.randint(*PET_TRAIN_EXP_RANGE)
    pet_exp = pet['exp'] + gained
    pet_level = pet['level']
    leveled = False
    while pet_level < max_level and pet_exp >= PET_EXP_PER_LEVEL:
        pet_exp -= PET_EXP_PER_LEVEL
        pet_level += 1
        leveled = True
    run("UPDATE character_pets SET exp=?, level=? WHERE id=?", (pet_exp, pet_level, pet_id))
    add_dao_progress(char['id'], 'beasts', daily_cap=3)
    msg = f"训养灵宠,经验 +{gained}"
    if leveled:
        msg += f",灵宠升至{pet_level}级!"
    flash(msg, 'ok')
    return redirect(url_for('pet_sanctuary'))

@app.route('/pet/rename/<int:pet_id>', methods=['POST'])
@login_required
def pet_rename(pet_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    pet = q("SELECT * FROM character_pets WHERE id=? AND char_id=?", (pet_id, char['id']), one=True)
    if not pet:
        flash('灵宠不存在', 'error')
        return redirect(url_for('pet_sanctuary'))
    name = request.form.get('name', '').strip()[:12] or None
    run("UPDATE character_pets SET pet_name=? WHERE id=?", (name, pet_id))
    flash(f"已为它取名{name}" if name else '已清空名字', 'ok')
    return redirect(url_for('pet_sanctuary'))

@app.route('/pet/set_active/<int:pet_id>', methods=['POST'])
@login_required
def pet_set_active(pet_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    pet = q("SELECT * FROM character_pets WHERE id=? AND char_id=? AND location='roster'", (pet_id, char['id']), one=True)
    if not pet:
        flash('只能将身边(灵兽峰之外)的灵宠设为出战', 'error')
        return redirect(url_for('pet_sanctuary'))
    run("UPDATE characters SET equipped_pet_id=? WHERE id=?", (pet_id, char['id']))
    flash(f"{pet['pet_name'] or PET_TYPES[pet['pet_key']]['label']}已设为出战灵宠", 'ok')
    return redirect(url_for('pet_sanctuary'))

@app.route('/pet/relocate/<int:pet_id>/<location>', methods=['POST'])
@login_required
def pet_relocate(pet_id, location):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    pet = q("SELECT * FROM character_pets WHERE id=? AND char_id=?", (pet_id, char['id']), one=True)
    if not pet or pet['location'] not in ('roster', 'sanctuary', 'holding'):
        flash('灵宠不存在或状态不允许操作', 'error')
        return redirect(url_for('pet_sanctuary'))
    if location == 'sanctuary':
        run("UPDATE character_pets SET location='sanctuary', holding_expires_ts=0 WHERE id=?", (pet_id,))
        if char['equipped_pet_id'] == pet_id:
            run("UPDATE characters SET equipped_pet_id=NULL WHERE id=?", (char['id'],))
        flash('已送去灵兽峰安置', 'ok')
    elif location == 'roster':
        placed = _place_pet(char['id'], pet_id)
        flash('已召回身边' if placed else f'身边已满{PET_ROSTER_CAP}只,继续留在驿站(或灵兽峰)等待安排', 'ok' if placed else 'error')
    else:
        flash('无效的位置', 'error')
    return redirect(url_for('pet_sanctuary'))

@app.route('/pet/sanctuary')
@login_required
def pet_sanctuary():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    _resolve_pet_holding_expiry(char['id'])
    pets = q("""SELECT * FROM character_pets WHERE char_id=? AND location IN ('roster','sanctuary','holding')
                ORDER BY (id=?) DESC, id""", (char['id'], char['equipped_pet_id']))
    roster = [p for p in pets if p['location'] == 'roster']
    holding = [dict(p, hours_left=max(0, (p['holding_expires_ts'] - now_ts() + 3599) // 3600))
               for p in pets if p['location'] == 'holding']
    sanctuary = [p for p in pets if p['location'] == 'sanctuary']
    train_left = max(0, PET_TRAIN_DAILY_LIMIT - get_daily_counter(char['id'], 'pet_train'))
    can_adopt = bool(get_peak_specialty(char).get('pet'))
    adopt_left = max(0, PET_ADOPT_DAILY_LIMIT - get_daily_counter(char['id'], 'pet_adopt'))
    return render_template('pet_sanctuary.html', char=char, roster=roster, holding=holding, sanctuary=sanctuary,
                            roster_cap=PET_ROSTER_CAP, pet_types=PET_TYPES, pet_qualities=PET_QUALITIES,
                            pet_quality=pet_quality, pet_max_level=pet_max_level, pet_image_url=pet_image_url,
                            pet_train_cost=PET_TRAIN_STAMINA_COST, pet_train_limit=PET_TRAIN_DAILY_LIMIT,
                            pet_exp_per_level=PET_EXP_PER_LEVEL, train_left=train_left, can_adopt=can_adopt,
                            pet_adopt_cost=PET_ADOPT_STAMINA_COST, adopt_left=adopt_left)

# ── 寻找前世:五环节收窄标签,每环节完成后三选一,终局揭晓全宗独一份的历史名人前尘 ──────

def _pastlife_claimed_keys():
    return {r['pastlife_key'] for r in q("SELECT pastlife_key FROM characters WHERE pastlife_key IS NOT NULL")}

def _pastlife_event_ends_ts():
    row = q("SELECT pastlife_event_ends_ts FROM sect_config WHERE id=1", one=True)
    return row['pastlife_event_ends_ts'] if row else None

def _pastlife_recover_dead_path(char, claimed_keys):
    """若原本可行的前尘分支被别人抢先揭晓，退回到最近仍有候选人的分支。
    保留当前满进度，让玩家可以立即重新选择，不必再消耗体力。"""
    path = json.loads(char['pastlife_path_json'] or '[]')
    original_path = list(path)
    while path and not pastlife_candidates(path, claimed_keys):
        path.pop()
    if path != original_path:
        run("UPDATE characters SET pastlife_path_json=? WHERE id=?", (json.dumps(path), char['id']))
    return path, path != original_path

@app.route('/pastlife')
@login_required
def pastlife_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['realm_idx'] < PASTLIFE_UNLOCK_REALM_IDX and not char['pastlife_key']:
        flash(f"修为不足,需达到{REALMS[PASTLIFE_UNLOCK_REALM_IDX]['name']}方能溯查前尘", 'error')
        return redirect(url_for('home'))
    event_ends_ts = _pastlife_event_ends_ts()
    event_time_left = max(0, event_ends_ts - now_ts()) if event_ends_ts else None
    event_expired = bool(event_ends_ts and now_ts() >= event_ends_ts)
    claimed = _pastlife_claimed_keys()
    path, recovered = _pastlife_recover_dead_path(char, claimed)
    if recovered:
        flash('原定前尘已被同门抢先揭晓，已为你退回上一重迷雾，可立即重新择路。', 'ok')
    result = PAST_LIFE_FIGURES.get(char['pastlife_key']) if char['pastlife_key'] else None
    stage_idx = pastlife_stage_index(len(path))
    stage = PASTLIFE_STAGES[stage_idx]
    pending_choice = None
    if not result and char['pastlife_progress'] >= PASTLIFE_STAGE_THRESHOLD:
        pending_choice = pastlife_offer_options(path, claimed)
    attempts_left = max(0, PASTLIFE_DAILY_LIMIT - get_daily_counter(char['id'], 'pastlife_reflect'))
    path_labels = [PASTLIFE_TAG_LABELS[PASTLIFE_DIMENSIONS[i]][v] for i, v in enumerate(path)]
    shard_qtys = {tk: _material_qty(char['id'], pastlife_talent_shard_key(tk)) for tk in TALENTS}
    open_trades = q("""SELECT t.*, c.name offerer_name FROM pastlife_shard_trades t
                        JOIN characters c ON c.id = t.offerer_char_id
                        WHERE t.status='open' ORDER BY t.created_ts DESC""")
    my_trade_count = sum(1 for t in open_trades if t['offerer_char_id'] == char['id'])
    return render_template('pastlife.html', char=char, result=result, stage=stage, stage_idx=stage_idx,
                            stages=PASTLIFE_STAGES, path_labels=path_labels,
                            progress=char['pastlife_progress'], threshold=PASTLIFE_STAGE_THRESHOLD,
                            pending_choice=pending_choice, attempts_left=attempts_left,
                            stamina_cost=PASTLIFE_STAMINA_COST, daily_limit=PASTLIFE_DAILY_LIMIT,
                            unlock_realm_name=REALMS[PASTLIFE_UNLOCK_REALM_IDX]['name'],
                            unlock_realm_idx=PASTLIFE_UNLOCK_REALM_IDX,
                            total_figures=len(PAST_LIFE_FIGURES),
                            shard_qtys=shard_qtys, has_shards=any(shard_qtys.values()),
                            TALENTS=TALENTS, open_trades=open_trades,
                            my_trade_count=my_trade_count, trade_max_active=PASTLIFE_SHARD_TRADE_MAX_ACTIVE,
                            event_time_left=event_time_left, event_expired=event_expired)

@app.route('/pastlife/reflect', methods=['POST'])
@login_required
def pastlife_reflect():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['pastlife_key']:
        flash('前尘已然揭晓,无需再溯', 'error')
        return redirect(url_for('pastlife_home'))
    ends_ts = _pastlife_event_ends_ts()
    if ends_ts and now_ts() >= ends_ts:
        flash('寻找前世活动已结束', 'error')
        return redirect(url_for('pastlife_home'))
    if char['realm_idx'] < PASTLIFE_UNLOCK_REALM_IDX:
        flash('修为不足', 'error')
        return redirect(url_for('pastlife_home'))
    if char['pastlife_progress'] >= PASTLIFE_STAGE_THRESHOLD:
        flash('此环节感悟已足,先做出抉择', 'error')
        return redirect(url_for('pastlife_home'))
    if get_daily_counter(char['id'], 'pastlife_reflect') >= PASTLIFE_DAILY_LIMIT:
        flash('今日已溯查多次,心神俱疲,明日再来', 'error')
        return redirect(url_for('pastlife_home'))
    char = sync_stamina(char)
    if char['stamina'] < PASTLIFE_STAMINA_COST:
        flash('体力不足', 'error')
        return redirect(url_for('pastlife_home'))
    run("UPDATE characters SET stamina=stamina-? WHERE id=?", (PASTLIFE_STAMINA_COST, char['id']))
    bump_daily_counter(char['id'], 'pastlife_reflect')
    path = json.loads(char['pastlife_path_json'] or '[]')
    dim = PASTLIFE_STAGES[pastlife_stage_index(len(path))]['key']
    gained = random.randint(*PASTLIFE_PROGRESS_RANGE)
    new_progress = min(PASTLIFE_STAGE_THRESHOLD, char['pastlife_progress'] + gained)
    run("UPDATE characters SET pastlife_progress=? WHERE id=?", (new_progress, char['id']))
    material_key = random.choices(list(PASTLIFE_MATERIAL_TIER_WEIGHTS.keys()),
                                   weights=list(PASTLIFE_MATERIAL_TIER_WEIGHTS.values()), k=1)[0]
    _grant_material(char['id'], material_key, 1)
    gain_desc = f"前尘感悟+{gained},拾得{MATERIAL_LABELS[material_key]}×1"
    if random.random() < PASTLIFE_TALENT_SHARD_CHANCE:
        shard_talent_key = random.choice(list(TALENTS.keys()))
        shard_key = pastlife_talent_shard_key(shard_talent_key)
        _grant_material(char['id'], shard_key, 1)
        gain_desc += f"、{MATERIAL_LABELS[shard_key]}×1"
    flash(f"{random.choice(PASTLIFE_PROGRESS_FLAVORS[dim])}({gain_desc})", 'ok')
    return redirect(url_for('pastlife_home'))

@app.route('/pastlife/talent_exchange', methods=['POST'])
@login_required
def pastlife_talent_exchange():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['pastlife_talent_exchanged']:
        flash('此生凝聚传承血脉碎片的机缘只有一次,你已经用过了', 'error')
        return redirect(url_for('bag_home'))
    talent_key = request.form.get('talent_key', '')
    if talent_key not in TALENTS:
        flash('传承/血脉不存在', 'error')
        return redirect(url_for('bag_home'))
    if char['talent_key'] == talent_key:
        flash('已是此传承/血脉,无需更换', 'error')
        return redirect(url_for('bag_home'))
    shard_key = pastlife_talent_shard_key(talent_key)
    if not _consume_materials(char['id'], {shard_key: PASTLIFE_TALENT_SHARD_COST}):
        flash(f"{MATERIAL_LABELS[shard_key]}不足{PASTLIFE_TALENT_SHARD_COST}片", 'error')
        return redirect(url_for('bag_home'))
    old_key = char['talent_key']
    run("UPDATE characters SET talent_key=?, pastlife_talent_exchanged=1 WHERE id=?", (talent_key, char['id']))
    label = TALENTS[talent_key]['label']
    if old_key:
        flash(f"前尘碎片凝聚,你舍{TALENTS[old_key]['label']}、换得「{label}」!此生仅此一次,不可再更换", 'ok')
    else:
        flash(f"前尘碎片凝聚成型,你自此身负「{label}」之能!此生仅此一次,不可再更换", 'ok')
    return redirect(url_for('bag_home'))

@app.route('/pastlife/talent_reinforce', methods=['POST'])
@login_required
def pastlife_talent_reinforce():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not char['talent_key']:
        flash('尚未凝聚传承/血脉,无从强化', 'error')
        return redirect(url_for('bag_home'))
    shard_key = pastlife_talent_shard_key(char['talent_key'])
    if not _consume_materials(char['id'], {shard_key: PASTLIFE_TALENT_REINFORCE_COST}):
        flash(f"{MATERIAL_LABELS[shard_key]}不足{PASTLIFE_TALENT_REINFORCE_COST}片", 'error')
        return redirect(url_for('bag_home'))
    run("UPDATE characters SET talent_reinforce_count=talent_reinforce_count+1 WHERE id=?", (char['id'],))
    flash(f"「{TALENTS[char['talent_key']]['label']}」愈发精纯,攻击+{PASTLIFE_TALENT_REINFORCE_ATTACK_BONUS}、"
          f"防御+{PASTLIFE_TALENT_REINFORCE_DEFENSE_BONUS}(可反复强化)", 'ok')
    return redirect(url_for('bag_home'))

# ── 碎片交换板:同门碎片不够、手里攒了别门用不上的,挂出1换1;创建即抵押,撤销即退回,
# 成交则双方各自收一封带附件的邮件去领,不直接进背包——保留跟其他"附件邮件"一致的领取仪式感 ──

@app.route('/pastlife/shard_trade/create', methods=['POST'])
@login_required
def pastlife_shard_trade_create():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    offer_key = request.form.get('offer_talent_key', '')
    want_key = request.form.get('want_talent_key', '')
    if offer_key not in TALENTS or want_key not in TALENTS:
        flash('传承/血脉不存在', 'error')
        return redirect(url_for('pastlife_home'))
    if offer_key == want_key:
        flash('不能用同一门碎片交换自己', 'error')
        return redirect(url_for('pastlife_home'))
    active_count = q("SELECT COUNT(*) c FROM pastlife_shard_trades WHERE offerer_char_id=? AND status='open'",
                      (char['id'],), one=True)['c']
    if active_count >= PASTLIFE_SHARD_TRADE_MAX_ACTIVE:
        flash(f"挂出的交换请求已达上限({PASTLIFE_SHARD_TRADE_MAX_ACTIVE}条),先撤销一些再来", 'error')
        return redirect(url_for('pastlife_home'))
    offer_shard_key = pastlife_talent_shard_key(offer_key)
    if not _consume_materials(char['id'], {offer_shard_key: 1}):
        flash(f"{MATERIAL_LABELS[offer_shard_key]}不足1片", 'error')
        return redirect(url_for('pastlife_home'))
    run("""INSERT INTO pastlife_shard_trades (offerer_char_id,offer_talent_key,want_talent_key,status,created_ts)
           VALUES (?,?,?,'open',?)""", (char['id'], offer_key, want_key, now_ts()))
    flash(f"已挂出:用{TALENTS[offer_key]['label']}碎片×1 换 {TALENTS[want_key]['label']}碎片×1,静候有缘人", 'ok')
    return redirect(url_for('pastlife_home'))

@app.route('/pastlife/shard_trade/<int:trade_id>/cancel', methods=['POST'])
@login_required
def pastlife_shard_trade_cancel(trade_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    trade = q("SELECT * FROM pastlife_shard_trades WHERE id=? AND offerer_char_id=? AND status='open'",
              (trade_id, char['id']), one=True)
    if not trade:
        flash('该交换请求不存在或已处理', 'error')
        return redirect(url_for('pastlife_home'))
    cur = run("UPDATE pastlife_shard_trades SET status='cancelled', resolved_ts=? WHERE id=? AND status='open'",
              (now_ts(), trade_id))
    if cur.rowcount == 0:
        flash('该交换请求刚被接受了,无法撤销', 'error')
        return redirect(url_for('pastlife_home'))
    _grant_material(char['id'], pastlife_talent_shard_key(trade['offer_talent_key']), 1)
    flash(f"已撤销,{TALENTS[trade['offer_talent_key']]['label']}碎片×1已退回行囊", 'ok')
    return redirect(url_for('pastlife_home'))

@app.route('/pastlife/shard_trade/<int:trade_id>/accept', methods=['POST'])
@login_required
def pastlife_shard_trade_accept(trade_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    trade = q("SELECT * FROM pastlife_shard_trades WHERE id=? AND status='open'", (trade_id,), one=True)
    if not trade:
        flash('该交换请求不存在或已处理', 'error')
        return redirect(url_for('pastlife_home'))
    if trade['offerer_char_id'] == char['id']:
        flash('不能接受自己的交换请求', 'error')
        return redirect(url_for('pastlife_home'))
    want_shard_key = pastlife_talent_shard_key(trade['want_talent_key'])
    if not _consume_materials(char['id'], {want_shard_key: 1}):
        flash(f"{MATERIAL_LABELS[want_shard_key]}不足1片,无法接受", 'error')
        return redirect(url_for('pastlife_home'))
    cur = run("""UPDATE pastlife_shard_trades SET status='completed', accepted_by_char_id=?, resolved_ts=?
                 WHERE id=? AND status='open'""", (char['id'], now_ts(), trade_id))
    if cur.rowcount == 0:
        _grant_material(char['id'], want_shard_key, 1)
        flash('手慢了,该交换请求刚被别人接走', 'error')
        return redirect(url_for('pastlife_home'))
    offer_shard_key = pastlife_talent_shard_key(trade['offer_talent_key'])
    offer_label = MATERIAL_LABELS[offer_shard_key]
    want_label = MATERIAL_LABELS[want_shard_key]
    offerer_name = q("SELECT name FROM characters WHERE id=?", (trade['offerer_char_id'],), one=True)['name']
    send_system_mail(trade['offerer_char_id'], '碎片交换成交',
                      f"{char['name']}接受了你的交换请求,{want_label}×1已送达,请领取附件。",
                      attachment={'materials': {want_shard_key: 1}})
    send_system_mail(char['id'], '碎片交换成交',
                      f"你接受了{offerer_name}的交换请求,{offer_label}×1已送达,请领取附件。",
                      attachment={'materials': {offer_shard_key: 1}})
    flash(f"交换成交!{want_label}×1已寄至你的信箱,领取附件即可", 'ok')
    return redirect(url_for('pastlife_home'))

@app.route('/pastlife/choose', methods=['POST'])
@login_required
def pastlife_choose():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if char['pastlife_key']:
        flash('前尘已然揭晓', 'error')
        return redirect(url_for('pastlife_home'))
    if char['pastlife_progress'] < PASTLIFE_STAGE_THRESHOLD:
        flash('火候未到,尚需继续溯查', 'error')
        return redirect(url_for('pastlife_home'))
    claimed = _pastlife_claimed_keys()
    path, recovered = _pastlife_recover_dead_path(char, claimed)
    if recovered:
        flash('原定前尘已被同门抢先揭晓，请重新做出选择。', 'ok')
        return redirect(url_for('pastlife_home'))
    options = pastlife_offer_options(path, claimed)
    valid_values = {o['value'] for o in options}
    picked = request.form.get('value', '')
    if picked not in valid_values:
        flash('这段前尘已然模糊,请重新感应', 'error')
        return redirect(url_for('pastlife_home'))
    path = path + [picked]
    if len(path) >= len(PASTLIFE_DIMENSIONS):
        candidates = pastlife_candidates(path, claimed) or [k for k in PAST_LIFE_FIGURES if k not in claimed]
        result_key = random.choice(candidates)
        fig = PAST_LIFE_FIGURES[result_key]
        run("UPDATE characters SET pastlife_key=?, pastlife_path_json=?, pastlife_progress=0 WHERE id=?",
            (result_key, json.dumps(path), char['id']))
        title = title_for(char['join_seq'], char['gender'])
        msg = f"前尘尽显,识海之中一道身影渐渐清晰——原来你此生的前尘,竟是那位{fig['epithet']}{fig['name']}!"
        send_system_mail(char['id'], '前尘揭晓', msg)
        for c in q("SELECT id FROM characters WHERE id != ?", (char['id'],)):
            send_system_mail(c['id'], '前尘轶闻',
                              f"{char['name']}({title})溯得前尘,竟是那位{fig['epithet']}{fig['name']},"
                              "此生因缘天下独一份,自此再无人能与之同名。", from_label='宗门公告')
        log_chronicle(f"{char['name']}({title})溯得前尘,乃{fig['name']}转世", major=True)
        check_achievements(char['id'])
        flash(msg, 'ok')
    else:
        run("UPDATE characters SET pastlife_path_json=?, pastlife_progress=0 WHERE id=?",
            (json.dumps(path), char['id']))
        flash('前尘又清晰了一分。', 'ok')
    return redirect(url_for('pastlife_home'))

# ── 炼丹(丹道峰):具体丹方,起手自带/炼丹顿悟/花贡献购买三条获取路 ─────────────────

def _known_recipe_keys(char_id):
    return {r['recipe_key'] for r in q("SELECT recipe_key FROM character_recipes WHERE char_id=?", (char_id,))}

def _pill_qty(char_id, recipe_key):
    row = q("SELECT qty FROM character_pills WHERE char_id=? AND recipe_key=?", (char_id, recipe_key), one=True)
    return row['qty'] if row else 0

@app.route('/alchemy')
@login_required
def alchemy_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('alchemy'):
        flash('唯有丹道峰弟子可炼丹', 'error')
        return redirect(url_for('home'))
    char = sync_stamina(char)
    known = _known_recipe_keys(char['id'])
    success_bonus = (char['alchemist_level'] - 1) * ALCHEMIST_SUCCESS_BONUS_PER_LEVEL
    known_recipes = []
    buyable_recipes = []
    for r in ALCHEMY_RECIPES:
        if r['key'] in known:
            rr = dict(r)
            rr['success_rate'] = min(ALCHEMIST_MAX_SUCCESS_RATE, r['base_success'] + success_bonus)
            rr['pill_qty'] = _pill_qty(char['id'], r['key'])
            rr['locked'] = char['alchemist_level'] < r['min_level']
            rr['has_materials'] = _has_materials(char['id'], r['material_cost'])
            rr['material_cost_desc'] = '、'.join(
                f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in r['material_cost'].items())
            known_recipes.append(rr)
        elif r['unlock'] == 'buy':
            buyable_recipes.append(r)
    crafted_today = get_daily_counter(char['id'], 'alchemy_craft')
    return render_template('alchemy.html', char=char, known_recipes=known_recipes, buyable_recipes=buyable_recipes,
                            level_name=alchemist_level_name(char['alchemist_level']),
                            exp_to_next=alchemist_exp_to_next(char['alchemist_level']),
                            max_level=ALCHEMIST_MAX_LEVEL, level_names=ALCHEMIST_LEVEL_NAMES,
                            crafted_today=crafted_today, diminish_after=ALCHEMY_DIMINISH_AFTER,
                            recycle_exp=ALCHEMY_RECYCLE_EXP)

@app.route('/alchemy/learn/<recipe_key>', methods=['POST'])
@login_required
def alchemy_learn(recipe_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('alchemy'):
        flash('唯有丹道峰弟子可学习丹方', 'error')
        return redirect(url_for('home'))
    recipe = ALCHEMY_RECIPES_BY_KEY.get(recipe_key)
    if not recipe or recipe['unlock'] != 'buy':
        flash('丹方不存在', 'error')
        return redirect(url_for('alchemy_home'))
    if recipe_key in _known_recipe_keys(char['id']):
        flash('你已学会此丹方', 'error')
        return redirect(url_for('alchemy_home'))
    cur = run("UPDATE characters SET contribution=contribution-? WHERE id=? AND contribution>=?",
              (recipe['buy_cost'], char['id'], recipe['buy_cost']))
    if cur.rowcount == 0:
        flash('贡献不足,无法购买此丹方', 'error')
        return redirect(url_for('alchemy_home'))
    try:
        run("INSERT INTO character_recipes (char_id,recipe_key,learned_ts) VALUES (?,?,?)",
            (char['id'], recipe_key, now_ts()))
    except sqlite3.IntegrityError:
        run("UPDATE characters SET contribution=contribution+? WHERE id=?", (recipe['buy_cost'], char['id']))
        flash('你已学会此丹方', 'error')
        return redirect(url_for('alchemy_home'))
    flash(f"习得丹方——{recipe['label']}", 'ok')
    return redirect(url_for('alchemy_home'))

@app.route('/alchemy/craft/<recipe_key>', methods=['POST'])
@login_required
def alchemy_craft(recipe_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('alchemy'):
        flash('唯有丹道峰弟子可炼丹', 'error')
        return redirect(url_for('home'))
    recipe = ALCHEMY_RECIPES_BY_KEY.get(recipe_key)
    if not recipe or recipe_key not in _known_recipe_keys(char['id']):
        flash('你尚未学会此丹方', 'error')
        return redirect(url_for('alchemy_home'))
    if char['alchemist_level'] < recipe['min_level']:
        flash('炼丹等阶不足,暂时炼不出此丹方', 'error')
        return redirect(url_for('alchemy_home'))
    if not _has_materials(char['id'], recipe['material_cost']):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in recipe['material_cost'].items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('alchemy_home'))
    if not _consume_materials(char['id'], recipe['material_cost']):
        flash('材料状态已变化,请刷新后重试', 'error')
        return redirect(url_for('alchemy_home'))
    crafted_today = get_daily_counter(char['id'], 'alchemy_craft')
    diminished = crafted_today >= ALCHEMY_DIMINISH_AFTER
    bump_daily_counter(char['id'], 'alchemy_craft')
    success_rate = min(ALCHEMIST_MAX_SUCCESS_RATE,
                        recipe['base_success'] + (char['alchemist_level'] - 1) * ALCHEMIST_SUCCESS_BONUS_PER_LEVEL
                        + dao_bonus(char['id'], 'craft_success_pct'))
    success = random.random() * 100 <= success_rate
    exp_gain = ALCHEMIST_EXP_ON_SUCCESS if success else ALCHEMIST_EXP_ON_FAIL
    if diminished:
        exp_gain = round(exp_gain * ALCHEMY_DIMINISH_MULT)
    new_exp = char['alchemist_exp'] + exp_gain
    new_level = char['alchemist_level']
    leveled = False
    while new_level < ALCHEMIST_MAX_LEVEL and new_exp >= (alchemist_exp_to_next(new_level) or 10 ** 9):
        new_exp -= alchemist_exp_to_next(new_level)
        new_level += 1
        leveled = True
    run("UPDATE characters SET alchemist_exp=?, alchemist_level=? WHERE id=?", (new_exp, new_level, char['id']))
    msg = ''
    if success:
        add_dao_progress(char['id'], 'creation', daily_cap=5)
        run("INSERT INTO character_pills (char_id,recipe_key,qty) VALUES (?,?,1) "
            "ON CONFLICT(char_id,recipe_key) DO UPDATE SET qty=qty+1", (char['id'], recipe_key))
        msg = f"炼丹成功,炼得{recipe['label']}一枚"
        known = _known_recipe_keys(char['id'])
        undiscovered = [r for r in ALCHEMY_RECIPES if r['unlock'] == 'discover'
                        and r['key'] not in known and r['min_level'] <= new_level]
        if undiscovered and random.random() < RECIPE_DISCOVER_CHANCE:
            found = random.choice(undiscovered)
            run("INSERT INTO character_recipes (char_id,recipe_key,learned_ts) VALUES (?,?,?)",
                (char['id'], found['key'], now_ts()))
            msg += f",炼丹时忽有所悟,习得新丹方——{found['label']}!"
    else:
        msg = '炼丹失败,丹炉中一片焦黑'
    if leveled:
        msg += f",炼丹造诣精进,晋为{alchemist_level_name(new_level)}!"
    check_achievements(char['id'])
    flash(msg, 'ok' if success else 'error')
    return redirect(url_for('alchemy_home'))

@app.route('/alchemy/consume/<recipe_key>', methods=['POST'])
@login_required
def alchemy_consume(recipe_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    recipe = ALCHEMY_RECIPES_BY_KEY.get(recipe_key)
    if not recipe or _pill_qty(char['id'], recipe_key) < 1:
        flash('你没有这种丹药', 'error')
        return redirect(url_for('alchemy_home'))
    run("UPDATE character_pills SET qty=qty-1 WHERE char_id=? AND recipe_key=?", (char['id'], recipe_key))
    apply_reward(char['id'], recipe['reward'])
    check_achievements(char['id'])
    flash(f"服下{recipe['label']},顿觉神清气爽", 'ok')
    return redirect(url_for('alchemy_home'))

@app.route('/alchemy/sell/<recipe_key>', methods=['POST'])
@login_required
def alchemy_sell(recipe_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    recipe = ALCHEMY_RECIPES_BY_KEY.get(recipe_key)
    if not recipe or _pill_qty(char['id'], recipe_key) < 1:
        flash('你没有这种丹药', 'error')
        return redirect(url_for('alchemy_home'))
    run("UPDATE character_pills SET qty=qty-1 WHERE char_id=? AND recipe_key=?", (char['id'], recipe_key))
    run("UPDATE characters SET lingshi=lingshi+? WHERE id=?", (recipe['sell_price'], char['id']))
    flash(f"卖出{recipe['label']}一枚,得灵石 {recipe['sell_price']}", 'ok')
    return redirect(url_for('alchemy_home'))

@app.route('/alchemy/recycle/<recipe_key>', methods=['POST'])
@login_required
def alchemy_recycle(recipe_key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    recipe = ALCHEMY_RECIPES_BY_KEY.get(recipe_key)
    if not recipe or _pill_qty(char['id'], recipe_key) < 1:
        flash('你没有这种丹药', 'error')
        return redirect(url_for('alchemy_home'))
    run("UPDATE character_pills SET qty=qty-1 WHERE char_id=? AND recipe_key=?", (char['id'], recipe_key))
    run("UPDATE characters SET alchemist_exp=alchemist_exp+? WHERE id=?", (ALCHEMY_RECYCLE_EXP, char['id']))
    flash(f"回炉{recipe['label']}一枚,得炼丹经验 {ALCHEMY_RECYCLE_EXP}", 'ok')
    return redirect(url_for('alchemy_home'))

def _element_display(element_key):
    """element_key 可能是普通五行('metal'等)或某个变异 key,统一返回 (显示名, 是否变异, 所属五行key)。"""
    if element_key in ELEMENTS:
        return ELEMENTS[element_key]['label'], False, element_key
    mutation = ELEMENT_MUTATIONS.get(element_key)
    if mutation:
        return mutation['label'], True, mutation['element']
    return element_key, False, element_key

@app.route('/forge')
@login_required
def forge_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('forge'):
        flash('唯有炼器峰弟子可炼器', 'error')
        return redirect(url_for('home'))
    weights = FORGE_CORE_QUALITY_WEIGHTS.get(char['forger_level'], FORGE_CORE_QUALITY_WEIGHTS[1])
    basic_gear = [dict(t, owned=_inventory_qty(char['id'], 'gear', t['key']) > 0)
                  for t in EQUIPMENT_BASIC_TEMPLATES]
    core_material_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in FORGE_CORE_MATERIAL_COST.items())
    gear_material_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in FORGE_GEAR_MATERIAL_COST.items())
    trinket_material_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}"
                                      for k, v in FORGE_MASTER_TRINKET_MATERIAL_COST.items())
    return render_template('forge.html', char=char,
                            level_name=forger_level_name(char['forger_level']),
                            exp_to_next=forger_exp_to_next(char['forger_level']),
                            max_level=FORGER_MAX_LEVEL, level_names=FORGER_LEVEL_NAMES,
                            core_material_cost=FORGE_CORE_MATERIAL_COST, core_material_desc=core_material_desc,
                            has_core_materials=_has_materials(char['id'], FORGE_CORE_MATERIAL_COST),
                            core_quality=char['artifact_core_quality'] or 'low',
                            ARTIFACT_CORE_QUALITIES=ARTIFACT_CORE_QUALITIES,
                            FORGE_CORE_QUALITY_ORDER=FORGE_CORE_QUALITY_ORDER, weights=weights,
                            basic_gear=basic_gear, gear_material_desc=gear_material_desc,
                            has_gear_materials=_has_materials(char['id'], FORGE_GEAR_MATERIAL_COST),
                            crafted_today=get_daily_counter(char['id'], 'forge_craft'),
                            diminish_after=FORGE_DIMINISH_AFTER,
                            FORGE_MASTER_TRINKET=FORGE_MASTER_TRINKET,
                            trinket_material_desc=trinket_material_desc,
                            has_trinket_materials=_has_materials(char['id'], FORGE_MASTER_TRINKET_MATERIAL_COST))

@app.route('/forge/craft', methods=['POST'])
@login_required
def forge_craft():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('forge'):
        flash('唯有炼器峰弟子可炼器', 'error')
        return redirect(url_for('home'))
    if not char['artifact_core_bound']:
        flash('尚未绑定本命法宝,无从炼化', 'error')
        return redirect(url_for('forge_home'))
    if not _has_materials(char['id'], FORGE_CORE_MATERIAL_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in FORGE_CORE_MATERIAL_COST.items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('forge_home'))
    if not _consume_materials(char['id'], FORGE_CORE_MATERIAL_COST):
        flash('材料状态已变化,请刷新后重试', 'error')
        return redirect(url_for('forge_home'))
    diminished = get_daily_counter(char['id'], 'forge_craft') >= FORGE_DIMINISH_AFTER
    bump_daily_counter(char['id'], 'forge_craft')

    weights = FORGE_CORE_QUALITY_WEIGHTS.get(char['forger_level'], FORGE_CORE_QUALITY_WEIGHTS[1])
    rolled = random.choices(FORGE_CORE_QUALITY_ORDER, weights=[weights[k] for k in FORGE_CORE_QUALITY_ORDER], k=1)[0]
    current = char['artifact_core_quality'] or 'low'
    upgraded = ARTIFACT_CORE_QUALITY_ORDER.index(rolled) > ARTIFACT_CORE_QUALITY_ORDER.index(current)

    exp_gain = FORGER_EXP_ON_SUCCESS if upgraded else FORGER_EXP_ON_FAIL
    if diminished:
        exp_gain = round(exp_gain * FORGE_DIMINISH_MULT)
    new_exp = char['forger_exp'] + exp_gain
    new_level = char['forger_level']
    leveled = False
    while new_level < FORGER_MAX_LEVEL and new_exp >= (forger_exp_to_next(new_level) or 10 ** 9):
        new_exp -= forger_exp_to_next(new_level)
        new_level += 1
        leveled = True

    if upgraded:
        add_dao_progress(char['id'], 'creation', daily_cap=5)
        run("UPDATE characters SET artifact_core_quality=?, forger_exp=?, forger_level=? WHERE id=?",
            (rolled, new_exp, new_level, char['id']))
        msg = f"炼器有成,本命法宝品级精进,晋为{ARTIFACT_CORE_QUALITIES[rolled]['label']}!"
    else:
        run("UPDATE characters SET forger_exp=?, forger_level=? WHERE id=?", (new_exp, new_level, char['id']))
        msg = f"炼器未能超越现有品级({ARTIFACT_CORE_QUALITIES[current]['label']}),略有心得"
    if leveled:
        msg += f" 炼器造诣精进,晋为{forger_level_name(new_level)}!"
    check_achievements(char['id'])
    flash(msg, 'ok')
    return redirect(url_for('forge_home'))

EQUIPMENT_BASIC_TEMPLATES_BY_KEY = {t['key']: t for t in EQUIPMENT_BASIC_TEMPLATES}

@app.route('/forge/craft_gear/<key>', methods=['POST'])
@login_required
def forge_craft_gear(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('forge'):
        flash('唯有炼器峰弟子可炼器', 'error')
        return redirect(url_for('home'))
    tpl = EQUIPMENT_BASIC_TEMPLATES_BY_KEY.get(key)
    if not tpl:
        flash('未知图纸', 'error')
        return redirect(url_for('forge_home'))
    if _inventory_qty(char['id'], 'gear', key) > 0:
        flash(f"{tpl['label']}已炼成,无需重复锻造", 'error')
        return redirect(url_for('forge_home'))
    if not _has_materials(char['id'], FORGE_GEAR_MATERIAL_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in FORGE_GEAR_MATERIAL_COST.items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('forge_home'))
    if not _consume_materials(char['id'], FORGE_GEAR_MATERIAL_COST):
        flash('材料状态已变化,请刷新后重试', 'error')
        return redirect(url_for('forge_home'))
    _inventory_grant(char['id'], 'gear', 1, key)
    add_dao_progress(char['id'], 'creation', daily_cap=5)
    flash(f"锻成{tpl['label']}一件,已收入行囊,可去装备页穿戴", 'ok')
    return redirect(url_for('forge_home'))

@app.route('/forge/craft_trinket', methods=['POST'])
@login_required
def forge_craft_trinket():
    """炼器尊者(炼器峰满级)专属:打造终身绑定的第五件装备"秘宝",不入行囊、不可交易、不可替换。"""
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if not get_peak_specialty(char).get('forge'):
        flash('唯有炼器峰弟子可炼器', 'error')
        return redirect(url_for('home'))
    if char['forger_level'] < FORGER_MAX_LEVEL:
        flash(f"须炼器造诣臻至{forger_level_name(FORGER_MAX_LEVEL)},方可打造此宝", 'error')
        return redirect(url_for('forge_home'))
    if char['equipped_trinket_key']:
        flash('秘宝终身仅此一件,已然打造过', 'error')
        return redirect(url_for('forge_home'))
    if not _has_materials(char['id'], FORGE_MASTER_TRINKET_MATERIAL_COST):
        cost_desc = '、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}" for k, v in FORGE_MASTER_TRINKET_MATERIAL_COST.items())
        flash(f"材料不足,需{cost_desc}", 'error')
        return redirect(url_for('forge_home'))
    if not _consume_materials(char['id'], FORGE_MASTER_TRINKET_MATERIAL_COST):
        flash('材料状态已变化,请刷新后重试', 'error')
        return redirect(url_for('forge_home'))
    run("UPDATE characters SET equipped_trinket_key=? WHERE id=?", (FORGE_MASTER_TRINKET['key'], char['id']))
    check_achievements(char['id'])
    flash(f"毕生技艺凝于一印,{FORGE_MASTER_TRINKET['label']}打造功成,已自动佩戴,终身随身!", 'ok')
    return redirect(url_for('forge_home'))

# ── 交易行:寄售制,挂单即托管;物品可堆叠,灵宠按唯一活体连同身份与经历完整转移 ───────────

def _inventory_qty(char_id, item_kind, key1, key2=None, key3=None):
    if item_kind == 'pet':
        row = q("SELECT 1 FROM character_pets WHERE id=? AND char_id=? AND location!='listed'",
                (int(key1), char_id), one=True)
        return 1 if row else 0
    if item_kind == 'material':
        return _material_qty(char_id, key1)
    if item_kind == 'pill':
        row = q("SELECT qty FROM character_pills WHERE char_id=? AND recipe_key=?", (char_id, key1), one=True)
        return row['qty'] if row else 0
    if item_kind == 'artifact':
        row = q("SELECT qty FROM character_artifacts WHERE char_id=? AND form=? AND element_key=? AND rarity_key=?",
                (char_id, key1, key2, key3), one=True)
        return row['qty'] if row else 0
    if item_kind == 'gear':
        row = q("SELECT qty FROM character_equipment WHERE char_id=? AND item_key=?", (char_id, key1), one=True)
        return row['qty'] if row else 0
    return 0

def _inventory_consume(char_id, item_kind, qty, key1, key2=None, key3=None):
    """按 qty>=待扣数 才真正扣减,避免并发重复提交把库存扣成负数;返回是否扣减成功。"""
    if item_kind == 'pet':
        if qty != 1:
            return False
        pet_id = int(key1)
        cur = run("UPDATE character_pets SET location='listed' WHERE id=? AND char_id=? AND location!='listed'",
                  (pet_id, char_id))
        if cur.rowcount:
            run("UPDATE characters SET equipped_pet_id=NULL WHERE id=? AND equipped_pet_id=?", (char_id, pet_id))
    elif item_kind == 'material':
        cur = run("UPDATE character_materials SET qty=qty-? WHERE char_id=? AND material_key=? AND qty>=?",
                   (qty, char_id, key1, qty))
    elif item_kind == 'pill':
        cur = run("UPDATE character_pills SET qty=qty-? WHERE char_id=? AND recipe_key=? AND qty>=?",
                   (qty, char_id, key1, qty))
    elif item_kind == 'artifact':
        cur = run("""UPDATE character_artifacts SET qty=qty-? WHERE char_id=? AND form=? AND element_key=?
                     AND rarity_key=? AND qty>=?""", (qty, char_id, key1, key2, key3, qty))
    elif item_kind == 'gear':
        cur = run("UPDATE character_equipment SET qty=qty-? WHERE char_id=? AND item_key=? AND qty>=?",
                   (qty, char_id, key1, qty))
    else:
        return False
    return cur.rowcount > 0

def _inventory_grant(char_id, item_kind, qty, key1, key2=None, key3=None):
    if item_kind == 'pet':
        if qty != 1:
            return
        pet_id = int(key1)
        buyer = q("SELECT name FROM characters WHERE id=?", (char_id,), one=True)
        pet = q("SELECT history FROM character_pets WHERE id=?", (pet_id,), one=True)
        if not buyer or not pet:
            return
        history = pet['history'] or ''
        history += (f"；寄售后由{buyer['name']}接回" if key3 == 'cancel'
                    else f"；后由{buyer['name']}从交易行购得")
        run("UPDATE character_pets SET char_id=?, history=? WHERE id=?", (char_id, history.strip('；'), pet_id))
        _place_pet(char_id, pet_id)
    elif item_kind == 'material':
        _grant_material(char_id, key1, qty)
    elif item_kind == 'pill':
        run("INSERT INTO character_pills (char_id,recipe_key,qty) VALUES (?,?,?) "
            "ON CONFLICT(char_id,recipe_key) DO UPDATE SET qty=qty+?", (char_id, key1, qty, qty))
    elif item_kind == 'artifact':
        run("INSERT INTO character_artifacts (char_id,form,element_key,rarity_key,qty) VALUES (?,?,?,?,?) "
            "ON CONFLICT(char_id,form,element_key,rarity_key) DO UPDATE SET qty=qty+?",
            (char_id, key1, key2, key3, qty, qty))
    elif item_kind == 'gear':
        run("INSERT INTO character_equipment (char_id,item_key,qty) VALUES (?,?,?) "
            "ON CONFLICT(char_id,item_key) DO UPDATE SET qty=qty+?", (char_id, key1, qty, qty))
        row = q("SELECT lore FROM character_equipment WHERE char_id=? AND item_key=?", (char_id, key1), one=True)
        if row and not row['lore']:
            tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(key1, {})
            zone = next((z['label'] for z in MYSTIC_ZONES if z['key'] == tpl.get('zone')), '九霄仙门')
            run("UPDATE character_equipment SET lore=? WHERE char_id=? AND item_key=?",
                (roll_equipment_lore(zone), char_id, key1))

def _market_item_label(item_kind, key1, key2=None, key3=None):
    if item_kind == 'pet':
        pet = q("SELECT * FROM character_pets WHERE id=?", (int(key1),), one=True)
        if not pet:
            return '灵宠'
        species = PET_TYPES.get(pet['pet_key'], {}).get('label', pet['pet_key'])
        name = f"·{pet['pet_name']}" if pet['pet_name'] else ''
        return f"{pet['appearance'] or ''}{species}{name}"
    if item_kind == 'material':
        return MATERIAL_LABELS.get(key1, key1)
    if item_kind == 'pill':
        recipe = ALCHEMY_RECIPES_BY_KEY.get(key1)
        return recipe['label'] if recipe else key1
    if item_kind == 'artifact':
        elabel, _, _ = _element_display(key2)
        rlabel = FORGE_RARITIES_BY_KEY.get(key3, {}).get('label', key3)
        return f"{elabel}{key1}({rlabel})"
    if item_kind == 'gear':
        tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(key1)
        return tpl['label'] if tpl else key1
    return key1

@app.route('/market')
@login_required
def market_home():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    char = ensure_character_story(char)
    listings = q("""SELECT ml.*, c.name seller_name FROM market_listings ml
                     JOIN characters c ON c.id = ml.seller_char_id
                     WHERE ml.status='active' ORDER BY ml.created_ts DESC""")
    listing_views = []
    for l in listings:
        l = dict(l)
        l['label'] = _market_item_label(l['item_kind'], l['item_key'], l['item_key2'], l['item_key3'])
        l['pet_profile'] = q("SELECT * FROM character_pets WHERE id=?", (int(l['item_key']),), one=True) \
            if l['item_kind'] == 'pet' else None
        l['pet_quality_label'] = PET_QUALITIES[pet_quality(l['pet_profile']['pet_key'])]['label'] \
            if l['pet_profile'] else None
        l['is_mine'] = l['seller_char_id'] == char['id']
        listing_views.append(l)

    # 灵珠(合体渡劫·灵珠秘境专属材料)算绑定物品,不许上架交易,跟宗门制式装备不许转赠一个口径
    my_materials = [dict(r, label=MATERIAL_LABELS.get(r['material_key'], r['material_key']))
                     for r in q("SELECT * FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))
                     if r['material_key'] != 'lingzhu_bead']
    my_pills = [dict(r, label=ALCHEMY_RECIPES_BY_KEY.get(r['recipe_key'], {}).get('label', r['recipe_key']))
                for r in q("SELECT * FROM character_pills WHERE char_id=? AND qty>0", (char['id'],))]
    my_artifacts = [dict(r, label=_market_item_label('artifact', r['form'], r['element_key'], r['rarity_key']))
                     for r in q("SELECT * FROM character_artifacts WHERE char_id=? AND qty>0", (char['id'],))]
    my_gear = [dict(r, label=_market_item_label('gear', r['item_key']))
               for r in q("SELECT * FROM character_equipment WHERE char_id=? AND qty>0", (char['id'],))]
    my_pets = [dict(r, label=_market_item_label('pet', str(r['id'])),
                    quality_label=PET_QUALITIES[pet_quality(r['pet_key'])]['label'])
               for r in q("SELECT * FROM character_pets WHERE char_id=? AND location!='listed'", (char['id'],))]

    recent_trades = q("""SELECT mt.*, cs.name seller_name, cb.name buyer_name FROM market_trades mt
                          JOIN characters cs ON cs.id = mt.seller_char_id
                          JOIN characters cb ON cb.id = mt.buyer_char_id
                          ORDER BY mt.created_ts DESC LIMIT 20""")
    trade_views = []
    for t in recent_trades:
        t = dict(t)
        t['label'] = _market_item_label(t['item_kind'], t['item_key'], t['item_key2'], t['item_key3'])
        trade_views.append(t)

    active_count = q("SELECT COUNT(*) c FROM market_listings WHERE seller_char_id=? AND status='active'",
                      (char['id'],), one=True)['c']
    return render_template('market.html', char=char, listings=listing_views,
                            my_materials=my_materials, my_pills=my_pills, my_artifacts=my_artifacts,
                            my_gear=my_gear, my_pets=my_pets, pet_types=PET_TYPES, pet_image_url=pet_image_url,
                            recent_trades=trade_views, active_count=active_count,
                            max_active=MARKET_LISTING_MAX_ACTIVE, daily_limit=MARKET_LISTING_DAILY_LIMIT,
                            daily_used=get_daily_counter(char['id'], 'market_list'), tax_pct=MARKET_TAX_PCT)

@app.route('/market/list', methods=['POST'])
@login_required
def market_list_create():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    item_kind = request.form.get('item_kind')
    if item_kind not in ('material', 'pill', 'artifact', 'gear', 'pet'):
        flash('未知物品类型', 'error')
        return redirect(url_for('market_home'))
    key1 = request.form.get('key1', '').strip()
    key2 = request.form.get('key2', '').strip() or None
    key3 = request.form.get('key3', '').strip() or None
    qty = request.form.get('qty', type=int) or 0
    price = request.form.get('price', type=int) or 0
    if item_kind == 'material' and key1 == 'lingzhu_bead':
        flash('灵珠是渡劫路上的绑定之物,不可上架交易', 'error')
        return redirect(url_for('market_home'))
    if item_kind == 'pet':
        pet = q("SELECT id FROM character_pets WHERE id=? AND char_id=? AND location!='listed'",
                (key1, char['id']), one=True)
        if not pet:
            flash('灵宠不存在或已不在身边', 'error')
            return redirect(url_for('market_home'))
        qty = 1
        key2 = None
    if qty <= 0 or price < MARKET_MIN_PRICE:
        flash('数量或价格无效', 'error')
        return redirect(url_for('market_home'))
    active_count = q("SELECT COUNT(*) c FROM market_listings WHERE seller_char_id=? AND status='active'",
                      (char['id'],), one=True)['c']
    if active_count >= MARKET_LISTING_MAX_ACTIVE:
        flash('在架挂单已达上限,先下架一些再来', 'error')
        return redirect(url_for('market_home'))
    if get_daily_counter(char['id'], 'market_list') >= MARKET_LISTING_DAILY_LIMIT:
        flash('今日已上架多次,明日再来', 'error')
        return redirect(url_for('market_home'))
    if _inventory_qty(char['id'], item_kind, key1, key2, key3) < qty:
        flash('库存不足', 'error')
        return redirect(url_for('market_home'))
    if not _inventory_consume(char['id'], item_kind, qty, key1, key2, key3):
        flash('库存状态已变化,请刷新后重试', 'error')
        return redirect(url_for('market_home'))
    run("""INSERT INTO market_listings (seller_char_id,item_kind,item_key,item_key2,item_key3,
           qty_total,qty_remaining,price_per_unit,status,created_ts) VALUES (?,?,?,?,?,?,?,?,'active',?)""",
        (char['id'], item_kind, key1, key2, key3, qty, qty, price, now_ts()))
    bump_daily_counter(char['id'], 'market_list')
    flash(f"已上架{_market_item_label(item_kind, key1, key2, key3)}×{qty},单价{price}灵石", 'ok')
    return redirect(url_for('market_home'))

@app.route('/market/<int:listing_id>/buy', methods=['POST'])
@login_required
def market_buy(listing_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    listing = q("SELECT * FROM market_listings WHERE id=? AND status='active'", (listing_id,), one=True)
    if not listing:
        flash('该挂单已失效', 'error')
        return redirect(url_for('market_home'))
    if listing['seller_char_id'] == char['id']:
        flash('不可购买自己的挂单', 'error')
        return redirect(url_for('market_home'))
    qty = request.form.get('qty', type=int) or 0
    if listing['item_kind'] == 'pet':
        qty = 1
    if qty <= 0 or qty > listing['qty_remaining']:
        flash('购买数量无效', 'error')
        return redirect(url_for('market_home'))
    total_cost = qty * listing['price_per_unit']
    if char['lingshi'] < total_cost:
        flash('灵石不足', 'error')
        return redirect(url_for('market_home'))

    cur = run("UPDATE market_listings SET qty_remaining=qty_remaining-? WHERE id=? AND qty_remaining>=?",
              (qty, listing_id, qty))
    if cur.rowcount == 0:
        flash('手慢了,库存已被买光', 'error')
        return redirect(url_for('market_home'))

    tax = round(total_cost * MARKET_TAX_PCT / 100)
    seller_gain = total_cost - tax
    cur = run("UPDATE characters SET lingshi=lingshi-? WHERE id=? AND lingshi>=?",
              (total_cost, char['id'], total_cost))
    if cur.rowcount == 0:
        # 钱没扣成(并发抢购导致余额被别的操作先花掉了),把刚预留的库存还回去,不让买家白扣库存
        run("UPDATE market_listings SET qty_remaining=qty_remaining+?, status='active' WHERE id=?", (qty, listing_id))
        flash('灵石不足', 'error')
        return redirect(url_for('market_home'))
    run("UPDATE market_listings SET status='sold_out' WHERE id=? AND qty_remaining=0", (listing_id,))
    run("UPDATE characters SET lingshi=lingshi+? WHERE id=?", (seller_gain, listing['seller_char_id']))
    run("""INSERT INTO market_trades (listing_id,seller_char_id,buyer_char_id,item_kind,item_key,item_key2,item_key3,
           qty,price_per_unit,created_ts) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (listing_id, listing['seller_char_id'], char['id'], listing['item_kind'], listing['item_key'],
         listing['item_key2'], listing['item_key3'], qty, listing['price_per_unit'], now_ts()))
    _inventory_grant(char['id'], listing['item_kind'], qty, listing['item_key'], listing['item_key2'], listing['item_key3'])

    label = _market_item_label(listing['item_kind'], listing['item_key'], listing['item_key2'], listing['item_key3'])
    send_system_mail(listing['seller_char_id'], '交易行成交',
                      f"{char['name']}购入你寄售的{label}×{qty},获灵石{seller_gain}(已扣{MARKET_TAX_PCT}%手续费)。")
    flash(f"购得{label}×{qty},花费灵石{total_cost}", 'ok')
    return redirect(url_for('market_home'))

@app.route('/market/<int:listing_id>/cancel', methods=['POST'])
@login_required
def market_cancel(listing_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    listing = q("SELECT * FROM market_listings WHERE id=? AND seller_char_id=? AND status='active'",
                (listing_id, char['id']), one=True)
    if not listing:
        flash('挂单不存在', 'error')
        return redirect(url_for('market_home'))
    cur = run("UPDATE market_listings SET status='cancelled' WHERE id=? AND status='active'", (listing_id,))
    if cur.rowcount == 0:
        flash('挂单状态已变化,请刷新重试', 'error')
        return redirect(url_for('market_home'))
    if listing['qty_remaining'] > 0:
        _inventory_grant(char['id'], listing['item_kind'], listing['qty_remaining'],
                          listing['item_key'], listing['item_key2'],
                          'cancel' if listing['item_kind'] == 'pet' else listing['item_key3'])
    flash('已下架,库存已退回', 'ok')
    return redirect(url_for('market_home'))

# ── 宗门花名录 / 排行榜 ──────────────────────────────────────────────────────────

@app.route('/roster')
@login_required
def roster():
    char = me_character()
    # 无在世角色（尚未创建 / 已飞升退场）时仍允许只读查看花名录，不再拦回创建角色页——
    # 只是没有「请教」按钮（那个动作需要一个在世角色发起）。
    if char:
        # 服务热更时也立即应用新辈分规则，不必等待下次重启。
        _normalize_real_join_sequences(get_db())
        char = me_character()
    # 已飞升的NPC(开服元老让贤那批)退场即止,不留在花名录里占位置——真实弟子的飞升记录仍要留着,
    # 这里只筛掉 is_npc=1 且 ascended=1 的那部分。
    # 已飞升的排在最前面,按飞升先后排;其余人仍按原先的档位/入门序排。
    members = q("""SELECT characters.*, peaks.name peak_name FROM characters
                   LEFT JOIN peaks ON peaks.id = characters.peak_id
                   WHERE NOT (characters.is_npc=1 AND characters.ascended=1)
                   ORDER BY characters.ascended DESC, characters.ascend_ts ASC,
                            rank_tier DESC, join_seq ASC""")
    return render_template('roster.html', members=members, rank_by_tier=rank_by_tier,
                            title_for=title_for, realm_by_index=realm_by_index,
                            spirit_root_label=spirit_root_label,
                            spirit_root_elements_label=spirit_root_elements_label,
                            TALENTS=TALENTS, IMMORTAL_BONES=IMMORTAL_BONES,
                            me_id=char['id'] if char else None)

@app.route('/chronicle')
@login_required
def chronicle():
    cfg = q("SELECT founded_ts FROM sect_config WHERE id=1", one=True)
    sect_year = game_year_of(now_ts(), cfg['founded_ts'])
    entries = q("SELECT * FROM chronicle ORDER BY created_ts DESC LIMIT 200")
    return render_template('chronicle.html', entries=entries, sect_year=sect_year)

# ── 内部接口:给同一台机器上的QQ机器人轮询用,播报全宗大事记(is_major=1的那部分) ──────────
# 不接入登录态,靠共享token鉴权(X-Jiuxiao-Token头,与 INTERNAL_API_TOKEN 环境变量比对)

@app.route('/api/chronicle/major')
def api_chronicle_major():
    if not INTERNAL_API_TOKEN or request.headers.get('X-Jiuxiao-Token') != INTERNAL_API_TOKEN:
        return jsonify(error='unauthorized'), 401
    since_id = request.args.get('since_id', type=int) or 0
    rows = q("SELECT id,year,text,created_ts FROM chronicle WHERE is_major=1 AND id>? ORDER BY id ASC LIMIT 20",
             (since_id,))
    entries = [dict(r) for r in rows]
    latest_id = entries[-1]['id'] if entries else since_id
    return jsonify(entries=entries, latest_id=latest_id)

@app.route('/rankings')
@login_required
def rankings():
    by_realm = q("SELECT * FROM characters WHERE is_npc=0 ORDER BY realm_idx DESC, exp DESC LIMIT 50")
    by_contribution = q("SELECT * FROM characters WHERE is_npc=0 ORDER BY total_contribution DESC LIMIT 50")
    by_peak = q("""SELECT peaks.*, elder.name elder_name, COUNT(m.id) disciple_count,
                          COALESCE(SUM(m.realm_idx),0) + COALESCE(elder.realm_idx,0) power_score
                   FROM peaks LEFT JOIN characters elder ON elder.id = peaks.elder_id
                   LEFT JOIN characters m ON m.peak_id = peaks.id AND m.id != peaks.elder_id
                   GROUP BY peaks.id ORDER BY power_score DESC""")
    me = me_character()
    return render_template('rankings.html', by_realm=by_realm, by_contribution=by_contribution,
                            by_peak=by_peak, realm_by_index=realm_by_index,
                            title_for=title_for, me_id=me['id'] if me else None)

# ── 站内信 ─────────────────────────────────────────────────────────────────────

@app.route('/mail')
@login_required
def mail_inbox():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    mails = q("SELECT * FROM mail WHERE char_id=? ORDER BY created_ts DESC", (char['id'],))
    run("UPDATE mail SET read=1 WHERE char_id=? AND read=0", (char['id'],))
    mails_view = []
    for m in mails:
        m = dict(m)
        m['attachment'] = json.loads(m['attachment_json']) if m['attachment_json'] else None
        m['direction'] = 'in'
        mails_view.append(m)
    sent = q("""SELECT mail.*, characters.name recipient_name FROM mail
                JOIN characters ON characters.id = mail.char_id
                WHERE mail.from_char_id=? ORDER BY mail.created_ts DESC""", (char['id'],))
    for m in sent:
        m = dict(m)
        m['direction'] = 'out'
        mails_view.append(m)
    mails_view.sort(key=lambda m: m['created_ts'], reverse=True)
    # 带未领取附件的信不管多老都保留,其余(已处理的收信+所有送出的信)只留最近 MAIL_INBOX_DISPLAY_LIMIT 封,
    # 不然系统信越攒越多,信箱没完没了地长。
    unclaimed_ids = {m['id'] for m in mails_view if m['direction'] == 'in' and m.get('attachment') and not m['claimed']}
    kept, hidden_count = [], 0
    for m in mails_view:
        if m['id'] in unclaimed_ids or len(kept) < MAIL_INBOX_DISPLAY_LIMIT:
            kept.append(m)
        else:
            hidden_count += 1
    mails_view = kept
    members = q("""SELECT id, name, join_seq, gender FROM characters
                   WHERE ascended=0 AND deceased=0 AND is_npc=0 AND id!=? ORDER BY join_seq ASC""", (char['id'],))
    return render_template('mail.html', mails=mails_view, members=members, title_for=title_for,
                            reward_desc=_reward_desc, hidden_count=hidden_count)

@app.route('/mail/<int:mail_id>/claim', methods=['POST'])
@login_required
def mail_claim(mail_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    m = q("SELECT * FROM mail WHERE id=? AND char_id=?", (mail_id, char['id']), one=True)
    if not m or not m['attachment_json'] or m['claimed']:
        return redirect(url_for('mail_inbox'))
    attachment = json.loads(m['attachment_json'])
    apply_reward(char['id'], attachment)
    for mk, mq in attachment.get('materials', {}).items():
        _grant_material(char['id'], mk, mq)
    for ek, eq in attachment.get('equipment', {}).items():
        _inventory_grant(char['id'], 'gear', eq, ek)
    run("UPDATE mail SET claimed=1 WHERE id=?", (mail_id,))
    flash('已领取附件', 'ok')
    return redirect(url_for('mail_inbox'))

# ── 礼包码兑换 ─────────────────────────────────────────────────────────────────

@app.route('/redeem', methods=['GET', 'POST'])
@login_required
def redeem():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        gc = q("SELECT * FROM gift_codes WHERE code=?", (code,), one=True)
        if not gc:
            flash('礼包码不存在', 'error')
        elif gc['used_count'] >= gc['max_uses']:
            flash('礼包码已达兑换上限', 'error')
        elif gc['expires_ts'] and gc['expires_ts'] < now_ts():
            flash('礼包码已过期', 'error')
        elif q("SELECT 1 FROM gift_code_uses WHERE gift_code_id=? AND char_id=?",
               (gc['id'], char['id']), one=True):
            flash('你已经兑换过这个礼包码了', 'error')
        else:
            reward = json.loads(gc['reward_json'])
            apply_reward(char['id'], reward)
            run("INSERT INTO gift_code_uses (gift_code_id,char_id,used_ts) VALUES (?,?,?)",
                (gc['id'], char['id'], now_ts()))
            run("UPDATE gift_codes SET used_count=used_count+1 WHERE id=?", (gc['id'],))
            flash(f"兑换成功,获得修为 +{reward.get('exp', 0)}、贡献 +{reward.get('contribution', 0)}、"
                  f"寿元 +{reward.get('lifespan_years', 0)}年", 'ok')
        return redirect(url_for('redeem'))
    return render_template('redeem.html')

# ── 宗门商店:用贡献兑换丹药道具,每种每日限购,给贡献一个持续消费出口 ─────────────────

@app.route('/shop')
@login_required
def shop_list():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    bought_today = {i['key']: get_daily_counter(char['id'], f"shop_{i['key']}") for i in SHOP_ITEMS}
    items = [dict(i, effect_desc=(_reward_desc(i['reward']) if i.get('reward') else
                                   f"{MATERIAL_LABELS.get(i['material']['key'], i['material']['key'])} +{i['material']['qty']}"
                                   if i.get('material') else ''))
             for i in SHOP_ITEMS]
    material_rows = q("SELECT * FROM character_materials WHERE char_id=? AND qty>0", (char['id'],))
    materials_owned = {r['material_key']: r['qty'] for r in material_rows}
    exchanged_today = {i['key']: get_daily_counter(char['id'], f"material_exchange_{i['key']}")
                        for i in MATERIAL_EXCHANGE_ITEMS}
    exchange_items = [dict(i, can_afford=_has_materials(char['id'], i['material_cost']),
                            cost_desc='、'.join(f"{MATERIAL_LABELS.get(k, k)}×{v}"
                                               for k, v in i['material_cost'].items()))
                       for i in MATERIAL_EXCHANGE_ITEMS]
    return render_template('shop.html', char=char, items=items, bought_today=bought_today,
                            shop_limit=SHOP_DAILY_LIMIT, exchange_items=exchange_items,
                            materials_owned=materials_owned, exchanged_today=exchanged_today,
                            MATERIAL_LABELS=MATERIAL_LABELS)

@app.route('/shop/<key>', methods=['POST'])
@login_required
def shop_buy(key):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    item = SHOP_ITEMS_BY_KEY.get(key)
    if not item:
        flash('道具不存在', 'error')
        return redirect(url_for('shop_list'))
    cost = item['cost']
    discount = get_peak_specialty(char).get('shop_discount_pct', 0)
    if discount:
        cost = round(cost * (1 - discount / 100))
    if char['contribution'] < cost:
        flash('贡献不足', 'error')
        return redirect(url_for('shop_list'))
    counter_key = f"shop_{key}"
    if get_daily_counter(char['id'], counter_key) >= SHOP_DAILY_LIMIT:
        flash('今日已购买该道具达上限', 'error')
        return redirect(url_for('shop_list'))
    cur = run("UPDATE characters SET contribution=contribution-? WHERE id=? AND contribution>=?",
              (cost, char['id'], cost))
    if cur.rowcount == 0:
        flash('贡献不足', 'error')
        return redirect(url_for('shop_list'))
    effect_parts = []
    if item.get('reward'):
        apply_reward(char['id'], item['reward'])
        effect_parts.append(_reward_desc(item['reward']))
    if item.get('material'):
        _grant_material(char['id'], item['material']['key'], item['material']['qty'])
        effect_parts.append(f"{MATERIAL_LABELS.get(item['material']['key'], item['material']['key'])} +{item['material']['qty']}")
    bump_daily_counter(char['id'], counter_key)
    check_achievements(char['id'])
    tag = f"({'、'.join(effect_parts)},已直接生效)" if effect_parts else ''
    flash(f"购得{item['label']}{tag}", 'ok')
    return redirect(url_for('shop_list'))

# ── 师承:discipleships 里 disciple_id 唯一,天然是一棵树,顺着 master_id 往上/往下走 ──

def get_lineage_ancestors(char_id, max_depth=10):
    chain = []
    current = char_id
    seen = {char_id}
    for _ in range(max_depth):
        row = q("SELECT master_id FROM discipleships WHERE disciple_id=? AND status='active'", (current,), one=True)
        if not row or row['master_id'] in seen:
            break
        chain.append(row['master_id'])
        seen.add(row['master_id'])
        current = row['master_id']
    if not chain:
        return []
    rows = q(f"SELECT * FROM characters WHERE id IN ({','.join('?' * len(chain))})", chain)
    by_id = {r['id']: r for r in rows}
    return [by_id[cid] for cid in chain if cid in by_id]

def get_lineage_descendants(char_id, max_depth=6):
    generations = []
    frontier = [char_id]
    seen = {char_id}
    for _ in range(max_depth):
        placeholders = ','.join('?' * len(frontier))
        rows = q(f"SELECT disciple_id FROM discipleships WHERE master_id IN ({placeholders}) AND status='active'",
                 frontier)
        next_ids = [r['disciple_id'] for r in rows if r['disciple_id'] not in seen]
        if not next_ids:
            break
        seen.update(next_ids)
        char_rows = q(f"SELECT * FROM characters WHERE id IN ({','.join('?' * len(next_ids))})", next_ids)
        generations.append(char_rows)
        frontier = next_ids
    return generations

# ── 花名录 · 角色详情 / 英杰阁(荣誉展示) ─────────────────────────────────────────

@app.route('/roster/<int:char_id>')
@login_required
def character_detail(char_id):
    target = q("SELECT characters.*, peaks.name peak_name FROM characters "
               "LEFT JOIN peaks ON peaks.id = characters.peak_id WHERE characters.id=?", (char_id,), one=True)
    if not target:
        flash('角色不存在', 'error')
        return redirect(url_for('roster'))
    target = dict(target)
    target = ensure_character_story(target)
    target_pets = [dict(r, quality_label=PET_QUALITIES[pet_quality(r['pet_key'])]['label'],
                        species_label=PET_TYPES.get(r['pet_key'], {}).get('label', r['pet_key']))
                   for r in q("""SELECT * FROM character_pets WHERE char_id=? AND location IN ('roster','sanctuary')
                                  ORDER BY (id=?) DESC, id""", (char_id, target['equipped_pet_id']))]
    as_master = q("SELECT c.name, c.id FROM discipleships d JOIN characters c ON c.id = d.disciple_id "
                  "WHERE d.master_id=? AND d.status='active'", (char_id,))
    as_disciple = q("SELECT c.name, c.id, c.zi FROM discipleships d JOIN characters c ON c.id = d.master_id "
                    "WHERE d.disciple_id=? AND d.status='active'", (char_id,), one=True)
    achievements = q("""SELECT achievement_defs.name, achievement_defs.description, char_achievements.achieved_ts
                        FROM char_achievements JOIN achievement_defs ON achievement_defs.key = char_achievements.achievement_key
                        WHERE char_achievements.char_id=? ORDER BY char_achievements.achieved_ts""", (char_id,))
    talent_info = None
    if target['talent_key']:
        pct, stat, is_major = talent_stage_pct(target['talent_key'], target['realm_idx'])
        talent_info = {'label': TALENTS[target['talent_key']]['label'],
                        'source': '血脉' if TALENTS[target['talent_key']]['source'] == 'bloodline' else '传承',
                        'pct': pct, 'stat': '修为' if stat == 'exp' else '贡献', 'is_major': is_major}
    bone_label = IMMORTAL_BONES[target['immortal_bone_key']]['label'] if target['immortal_bone_key'] else None
    bone_bonus = IMMORTAL_BONES[target['immortal_bone_key']]['bonus'] if target['immortal_bone_key'] else None
    pastlife = PAST_LIFE_FIGURES.get(target['pastlife_key']) if target['pastlife_key'] else None
    ancestors = get_lineage_ancestors(char_id)
    descendants = get_lineage_descendants(char_id)
    me = me_character()
    bond_status = {}
    if me:
        rows = q("""SELECT bond_type, status FROM bonds
                    WHERE (char_a_id=? AND char_b_id=?) OR (char_a_id=? AND char_b_id=?)""",
                 (me['id'], char_id, char_id, me['id']))
        bond_status = {r['bond_type']: r['status'] for r in rows}

    owned_decoration_keys = {r['decoration_key'] for r in q(
        "SELECT decoration_key FROM character_decorations WHERE char_id=?", (char_id,))}
    decoration_label_by_key = {t['decoration_key']: t['decoration_label'] for t in CAVE_TRAITS.values()}
    cave_info = {
        'name': target['cave_name'],
        'tier_label': cave_tier_info(target['cave_tier'])['label'],
        'scenery': target['cave_scenery'],
        'trait_labels': [CAVE_TRAITS[t]['label'] for t in cave_traits_list(target) if t in CAVE_TRAITS],
        'decoration_labels': [decoration_label_by_key[k] for k in owned_decoration_keys
                               if k in decoration_label_by_key],
    }
    target_dao = DAO_PATHS.get(target.get('dao_path_key'))
    story_tags = q("""SELECT encounter_key, tag_label, resolved_ts FROM character_story_encounters
                       WHERE char_id=? AND tag_label IS NOT NULL ORDER BY resolved_ts""", (char_id,))

    children = [sync_offspring_growth(o) for o in _my_offspring(char_id)]
    for o in children:
        if not o.get('archetype'):
            o['archetype'] = offspring_archetype(o['personality_key'], o['hobby_key'])
            o['life_event'] = o.get('life_event') or roll_offspring_life_event()
            run("UPDATE offspring SET archetype=?, life_event=? WHERE id=?",
                (o['archetype'], o['life_event'], o['id']))
        o['stage'] = offspring_stage(o['realm_idx'])
        o['realm_name'] = REALMS[o['realm_idx']]['name']
        o['spouse_name'] = (_party_field('offspring', o['spouse_offspring_id'], 'name')
                             if o['spouse_offspring_id'] else o['spouse_npc_name'])
        o['manyue_revealed'] = o['manyue_status'] == 'done'
        if o['manyue_revealed']:
            o['personality_label'] = OFFSPRING_PERSONALITIES.get(o['personality_key'], {}).get('label', '?')
            o['hobby_label'] = OFFSPRING_HOBBIES.get(o['hobby_key'], {}).get('label', '?')
        else:
            o['personality_label'] = o['hobby_label'] = o['archetype'] = None

    can_write_immortal = bool(target['ascended'] and me and me['id'] != target['id']
                               and any(r['id'] == target['id'] for r in _mortal_ascended_kin(me['id'])))

    return render_template('character_detail.html', target=target, rank=rank_by_tier(target['rank_tier']),
                            realm=realm_by_index(target['realm_idx']), title_for=title_for,
                            spirit_root_label=spirit_root_label,
                            spirit_root_elements_label=spirit_root_elements_label,
                            talent_info=talent_info, bone_label=bone_label, bone_bonus=bone_bonus, pastlife=pastlife,
                            pastlife_buff_label=PASTLIFE_COMBAT_BUFF_LABEL,
                            pastlife_atk_bonus=PASTLIFE_COMBAT_ATTACK_BONUS,
                            pastlife_def_bonus=PASTLIFE_COMBAT_DEFENSE_BONUS,
                            as_master=as_master, as_disciple=as_disciple, achievements=achievements,
                            me_id=me['id'] if me else None, bond_status=bond_status, bond_types=BOND_TYPES,
                            ancestors=ancestors, descendants=descendants,
                            ancestor_label=ancestor_label, descendant_label=descendant_label,
                            cave_info=cave_info, children=children, target_dao=target_dao, story_tags=story_tags,
                            target_pets=target_pets, pet_image_url=pet_image_url,
                            can_write_immortal=can_write_immortal)

@app.route('/hall')
@login_required
def hall():
    bone_holders = q("SELECT * FROM characters WHERE immortal_bone_key IS NOT NULL")
    talent_masters = q("SELECT * FROM characters WHERE talent_key IS NOT NULL AND realm_idx >= ? "
                       "ORDER BY realm_idx DESC", (TALENT_AWAKEN_REALM,))
    leaders_raw = q("""SELECT leader_history.*, c.name, c.join_seq, c.gender,
                              d.name defeated_by_name, d.join_seq defeated_by_join_seq, d.gender defeated_by_gender
                       FROM leader_history
                       JOIN characters c ON c.id = leader_history.char_id
                       LEFT JOIN characters d ON d.id = leader_history.defeated_by_char_id
                       ORDER BY leader_history.started_ts""")
    # 被挑落的单独一组;在位中/善终卸任(飞升或身故,没被打下来过)的归一组——不看当下是否还在位,
    # 只看这一任是怎么结束的。同一人可能不止一次卸任又再夺回来又再被打下去,按 char_id 合并,
    # 免得同一个名字在列表里重复出现好几行,合并后用"×N次"标出来。
    leaders_defeated_flat = [l for l in leaders_raw if l['end_reason'] == 'dethroned']
    leaders_undefeated = [l for l in leaders_raw if l['end_reason'] != 'dethroned']
    defeated_groups = {}
    for l in leaders_defeated_flat:
        g = defeated_groups.setdefault(l['char_id'], {'name': l['name'], 'join_seq': l['join_seq'],
                                                        'gender': l['gender'], 'defeaters': [], 'times': 0})
        g['times'] += 1
        label = f"{l['defeated_by_name']}({title_for(l['defeated_by_join_seq'], l['defeated_by_gender'])})"
        if label not in g['defeaters']:  # 同一人打下去好几次不重复列名字,次数照样按总次数算
            g['defeaters'].append(label)
    leaders_defeated = [dict(g, defeaters_label='、'.join(g['defeaters'])) for g in defeated_groups.values()]
    immortals = q("SELECT * FROM characters WHERE ascended=1 AND is_npc=0 ORDER BY ascend_ts ASC")
    companion_rows = q("""SELECT bonds.accepted_ts, ca.id ca_id, ca.name ca_name, ca.join_seq ca_seq, ca.gender ca_gender,
                                  cb.id cb_id, cb.name cb_name, cb.join_seq cb_seq, cb.gender cb_gender
                           FROM bonds JOIN characters ca ON ca.id = bonds.char_a_id
                                      JOIN characters cb ON cb.id = bonds.char_b_id
                           WHERE bonds.bond_type='companion' AND bonds.status='active'
                           ORDER BY bonds.accepted_ts""")
    offspring_rows = []
    for o in q("SELECT * FROM offspring ORDER BY generation, born_ts"):
        o = dict(o)
        o['stage'] = offspring_stage(o['realm_idx'])
        o['realm_name'] = REALMS[o['realm_idx']]['name']
        o['parent_a_name'] = _party_field(o['parent_a_kind'], o['parent_a_id'], 'name')
        o['parent_b_name'] = (o['parent_b_npc_name'] if o['parent_b_kind'] == 'npc'
                               else _party_field(o['parent_b_kind'], o['parent_b_id'], 'name'))
        o['spouse_name'] = (_party_field('offspring', o['spouse_offspring_id'], 'name')
                             if o['spouse_offspring_id'] else o['spouse_npc_name'])
        offspring_rows.append(o)
    xiaxia_rows = q("SELECT * FROM characters WHERE xiaxia_fame > 0 ORDER BY xiaxia_fame DESC LIMIT 10")
    pastlife_holders = q("SELECT * FROM characters WHERE pastlife_key IS NOT NULL")
    return render_template('hall.html', bone_holders=bone_holders, talent_masters=talent_masters,
                            leaders_defeated=leaders_defeated, leaders_undefeated=leaders_undefeated,
                            immortals=immortals, companion_rows=companion_rows, offspring_rows=offspring_rows,
                            xiaxia_rows=xiaxia_rows, xiaxia_title=xiaxia_title,
                            title_for=title_for, TALENTS=TALENTS, IMMORTAL_BONES=IMMORTAL_BONES,
                            pastlife_holders=pastlife_holders, PAST_LIFE_FIGURES=PAST_LIFE_FIGURES,
                            pastlife_total=len(PAST_LIFE_FIGURES), CELESTIAL_OFFICES=CELESTIAL_OFFICES)

# ── 墓园:寿终正寝的同门长眠于此(飞升者见英杰阁,不在此列)——每日限次扫墓,寄一段心意 ────

GRAVEYARD_SWEEP_DAILY_LIMIT = 3
GRAVEYARD_SWEEP_MIND_GAIN = 5
GRAVEYARD_SWEEP_MIND_GAIN_KIN = 12  # 若是自己的师父/徒弟/道侣/义结金兰,追思更深,心境回得更多
GRAVEYARD_INCENSE_LINGSHI_RATE = 1  # 1灵石=1点香火,愿添多少自己定,不设上限也不设每日次数(反正要花灵石)
GRAVEYARD_SWEEP_FLAVORS = [
    '你在墓前静立片刻,焚一炷香,心绪渐渐平复。',
    '你拂去墓碑上的尘土,默然良久,方才转身离去。',
    '你在墓前摆上一束野花,轻声道了几句家常。',
]
GRAVEYARD_SWEEP_FLAVORS_KIN = [
    '你在墓前久久伫立,往昔种种涌上心头,终是化作一声轻叹。',
    '你跪在墓前,絮絮说着这些年的事,像是对方仍能听见。',
    '你为墓碑描新了字迹,眼眶微热,心事却也松快了几分。',
]

def _graveyard_kin_check(char_id, dead_id):
    """判断扫墓者与逝者是否有师徒/羁绊之实,决定悼念深浅。"""
    if q("SELECT 1 FROM discipleships WHERE (master_id=? AND disciple_id=?) OR (master_id=? AND disciple_id=?)",
         (char_id, dead_id, dead_id, char_id), one=True):
        return True
    if q("""SELECT 1 FROM bonds WHERE (char_a_id=? AND char_b_id=?) OR (char_a_id=? AND char_b_id=?)""",
         (char_id, dead_id, dead_id, char_id), one=True):
        return True
    return False

@app.route('/graveyard')
@login_required
def graveyard():
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    cfg = q("SELECT founded_ts FROM sect_config WHERE id=1", one=True)
    rows = q("SELECT * FROM characters WHERE deceased=1 ORDER BY incense_count DESC, death_ts DESC")
    graves = []
    for r in rows:
        r = dict(r)
        r['death_year'] = game_year_of(r['death_ts'], cfg['founded_ts']) if r['death_ts'] else None
        r['is_kin'] = _graveyard_kin_check(char['id'], r['id'])
        graves.append(r)
    swept_today = get_daily_counter(char['id'], 'graveyard_sweep')
    return render_template('graveyard.html', char=char, graves=graves, title_for=title_for,
                            swept_today=swept_today, sweep_limit=GRAVEYARD_SWEEP_DAILY_LIMIT)

@app.route('/graveyard/sweep/<int:dead_id>', methods=['POST'])
@login_required
def graveyard_sweep(dead_id):
    char = me_character()
    if not char:
        return redirect(url_for('create_character'))
    dead = q("SELECT * FROM characters WHERE id=? AND deceased=1", (dead_id,), one=True)
    if not dead:
        flash('此人并未安葬于此', 'error')
        return redirect(url_for('graveyard'))
    if get_daily_counter(char['id'], 'graveyard_sweep') >= GRAVEYARD_SWEEP_DAILY_LIMIT:
        flash('今日已扫墓多次,该回去歇息了', 'error')
        return redirect(url_for('graveyard'))
    bump_daily_counter(char['id'], 'graveyard_sweep')
    is_kin = _graveyard_kin_check(char['id'], dead_id)
    gain = GRAVEYARD_SWEEP_MIND_GAIN_KIN if is_kin else GRAVEYARD_SWEEP_MIND_GAIN
    apply_reward(char['id'], {'mind_state': gain})
    incense_gain = 1  # 扫墓本身就计一份香火,不花灵石也算
    incense_msg = ''
    lingshi_offer = max(0, request.form.get('incense_lingshi', type=int) or 0)
    if lingshi_offer > 0:
        if _spend(char['id'], 'lingshi', lingshi_offer):
            incense_gain += lingshi_offer * GRAVEYARD_INCENSE_LINGSHI_RATE
            incense_msg = f",又添香油钱{lingshi_offer}灵石"
        else:
            flash('灵石不足,本次仅完成扫墓,未能添香油钱', 'error')
    run("UPDATE characters SET incense_count=incense_count+? WHERE id=?", (incense_gain, dead_id))
    flavor = random.choice(GRAVEYARD_SWEEP_FLAVORS_KIN if is_kin else GRAVEYARD_SWEEP_FLAVORS)
    flash(f"{flavor}(心境+{gain}{incense_msg})", 'ok')
    return redirect(url_for('graveyard'))

# ── 仙籍:飞升者已经退场,不再参与任何数值系统,但可偶尔"下凡"教养子嗣、寄信亲故、扫墓追思——
# 仅此三件事。刻意不动 me_character()(那是"角色已退场"这条边界本身,别的路由几乎全靠它挡住
# 已飞升的角色),而是单独开一套自成一体的入口,靠 user_id+ascended=1 直接查,不跟主玩法混着走。

def _immortal_char(char_id):
    uid = S.get('uid')
    if not uid:
        return None
    row = q("SELECT * FROM characters WHERE id=? AND user_id=? AND ascended=1", (char_id, uid), one=True)
    return dict(row) if row else None

def _kin_char_ids(char_id):
    """师徒/道侣义结/子嗣的另一位家长——不看对方在世还是已飞升,纯粹算关系,由调用方按需再过滤状态。"""
    ids = set()
    m = q("SELECT master_id FROM discipleships WHERE disciple_id=? AND status='active'", (char_id,), one=True)
    if m:
        ids.add(m['master_id'])
    for d in q("SELECT disciple_id FROM discipleships WHERE master_id=? AND status='active'", (char_id,)):
        ids.add(d['disciple_id'])
    for b in q("SELECT char_a_id, char_b_id FROM bonds WHERE status='active' AND (char_a_id=? OR char_b_id=?)",
               (char_id, char_id)):
        ids.add(b['char_a_id']); ids.add(b['char_b_id'])
    for o in q("""SELECT parent_a_kind,parent_a_id,parent_b_kind,parent_b_id FROM offspring
                  WHERE (parent_a_kind='character' AND parent_a_id=?) OR (parent_b_kind='character' AND parent_b_id=?)""",
               (char_id, char_id)):
        if o['parent_a_kind'] == 'character' and o['parent_a_id'] != char_id:
            ids.add(o['parent_a_id'])
        if o['parent_b_kind'] == 'character' and o['parent_b_id'] != char_id:
            ids.add(o['parent_b_id'])
    ids.discard(char_id)
    return ids

def _immortal_relations(char_id):
    """飞升者只认在世的这些至亲——不是随便什么人都能去信打扰。"""
    ids = _kin_char_ids(char_id)
    if not ids:
        return []
    placeholders = ','.join('?' * len(ids))
    return q(f"SELECT * FROM characters WHERE id IN ({placeholders}) AND deceased=0 AND ascended=0", tuple(ids))

def _mortal_ascended_kin(char_id):
    """镜像 _immortal_relations:在世的人这边能遥寄书信/赠礼的飞升至亲,同一套关系判定反过来查。"""
    ids = _kin_char_ids(char_id)
    if not ids:
        return []
    placeholders = ','.join('?' * len(ids))
    return q(f"SELECT * FROM characters WHERE id IN ({placeholders}) AND ascended=1", tuple(ids))

@app.route('/immortal')
@login_required
def immortal_home():
    uid = S.get('uid')
    immortals = q("SELECT * FROM characters WHERE user_id=? AND ascended=1 ORDER BY created_ts DESC", (uid,))
    return render_template('immortal_home.html', immortals=immortals, title_for=title_for,
                            CELESTIAL_OFFICES=CELESTIAL_OFFICES)

@app.route('/immortal/<int:char_id>')
@login_required
def immortal_detail(char_id):
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    offspring_rows = [dict(o, stage=offspring_stage(o['realm_idx']), realm_name=REALMS[o['realm_idx']]['name'])
                      for o in q("""SELECT * FROM offspring WHERE alive=1 AND
                                    ((parent_a_kind='character' AND parent_a_id=?) OR (parent_b_kind='character' AND parent_b_id=?))""",
                                 (char_id, char_id))]
    relations = _immortal_relations(char_id)
    cfg = q("SELECT founded_ts FROM sect_config WHERE id=1", one=True)
    graves = []
    for r in q("SELECT * FROM characters WHERE deceased=1 ORDER BY death_ts DESC"):
        if _graveyard_kin_check(char_id, r['id']):
            r = dict(r)
            r['death_year'] = game_year_of(r['death_ts'], cfg['founded_ts']) if r['death_ts'] else None
            graves.append(r)
    teach_left = {o['id']: max(0, OFFSPRING_TEACH_DAILY_LIMIT - get_daily_counter(char_id, f"offspring_teach_{o['id']}"))
                  for o in offspring_rows}
    mail_left = max(0, MAIL_DAILY_LIMIT - get_daily_counter(char_id, 'immortal_mail'))
    sweep_left = max(0, GRAVEYARD_SWEEP_DAILY_LIMIT - get_daily_counter(char_id, 'immortal_graveyard_sweep'))
    # 飞升前留下的行囊,可随信捎给在世至亲——跟 mail_compose 一个口径,绑定物品不列出来
    materials_owned = {r['material_key']: r['qty'] for r in q(
        "SELECT material_key, qty FROM character_materials WHERE char_id=? AND qty>0", (char_id,))
        if r['material_key'] != 'lingzhu_bead'}
    equipment_owned = [dict(r, label=EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('label', r['item_key']))
                       for r in q("SELECT item_key, qty FROM character_equipment WHERE char_id=? AND qty>0", (char_id,))
                       if EQUIPMENT_TEMPLATES_BY_KEY.get(r['item_key'], {}).get('zone') not in ('unique', 'sect')]
    # 赠礼阁在世那边一直能送(见 gift_send,未卡"对方须在世"),缺的只是飞升者这边查收/回应的入口
    pending_gifts = [_gift_view(r) for r in q("""SELECT g.*,c.name maker_name FROM bond_gifts g
        LEFT JOIN characters c ON c.id=g.maker_id WHERE g.recipient_id=? AND g.status='pending'
        ORDER BY g.gifted_ts DESC""", (char_id,))]
    # 在世至亲能寄信给飞升者(见 mail_compose 的 can_write_immortal 分支),但飞升者不走 me_character()
    # 那套(ascended=0 过滤会把它挡在外面),之前一直没有查收入口——这里单独查 mail 表补上。
    inbox_mails = q("SELECT * FROM mail WHERE char_id=? ORDER BY created_ts DESC", (char_id,))
    run("UPDATE mail SET read=1 WHERE char_id=? AND read=0", (char_id,))
    inbox_mails = [dict(m, attachment=json.loads(m['attachment_json']) if m['attachment_json'] else None)
                   for m in inbox_mails]
    unclaimed_ids = {m['id'] for m in inbox_mails if m['attachment'] and not m['claimed']}
    inbox_kept, inbox_hidden = [], 0
    for m in inbox_mails:
        if m['id'] in unclaimed_ids or len(inbox_kept) < MAIL_INBOX_DISPLAY_LIMIT:
            inbox_kept.append(m)
        else:
            inbox_hidden += 1
    inbox_mails = inbox_kept
    return render_template('immortal_detail.html', char=char, offspring_rows=offspring_rows, relations=relations,
                            graves=graves, title_for=title_for, CELESTIAL_OFFICES=CELESTIAL_OFFICES,
                            teach_left=teach_left, teach_limit=OFFSPRING_TEACH_DAILY_LIMIT,
                            mail_left=mail_left, mail_limit=MAIL_DAILY_LIMIT,
                            sweep_left=sweep_left, sweep_limit=GRAVEYARD_SWEEP_DAILY_LIMIT,
                            materials_owned=materials_owned, material_labels=MATERIAL_LABELS,
                            equipment_owned=equipment_owned, pending_gifts=pending_gifts,
                            inbox_mails=inbox_mails, inbox_hidden=inbox_hidden, reward_desc=_reward_desc)

@app.route('/immortal/<int:char_id>/mail/<int:mail_id>/claim', methods=['POST'])
@login_required
def immortal_mail_claim(char_id, mail_id):
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    m = q("SELECT * FROM mail WHERE id=? AND char_id=?", (mail_id, char_id), one=True)
    if not m or not m['attachment_json'] or m['claimed']:
        return redirect(url_for('immortal_detail', char_id=char_id))
    attachment = json.loads(m['attachment_json'])
    apply_reward(char_id, attachment)
    for mk, mq in attachment.get('materials', {}).items():
        _grant_material(char_id, mk, mq)
    for ek, eq in attachment.get('equipment', {}).items():
        _inventory_grant(char_id, 'gear', eq, ek)
    run("UPDATE mail SET claimed=1 WHERE id=?", (mail_id,))
    flash('已领取附件', 'ok')
    return redirect(url_for('immortal_detail', char_id=char_id))

@app.route('/immortal/<int:char_id>/offspring/<int:off_id>/teach', methods=['POST'])
@login_required
def immortal_offspring_teach(char_id, off_id):
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    if char_id not in _resolve_owner_chars('offspring', off_id):
        flash('无权教养此子嗣', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    off = q("SELECT * FROM offspring WHERE id=?", (off_id,), one=True)
    if not off or not off['alive']:
        flash('子嗣不存在', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    if off['frail_warned_ts']:
        flash(f"{off['name']}近来体弱,不宜此时下凡探视教养", 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    off = sync_offspring_growth(off)
    if off['realm_idx'] >= OFFSPRING_REALM_CAP_IDX:
        flash('此子境界已至封顶,不必再教', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    counter_key = f'offspring_teach_{off_id}'
    if get_daily_counter(char_id, counter_key) >= OFFSPRING_TEACH_DAILY_LIMIT:
        flash('今日已教养多次,该歇息了', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    bump_daily_counter(char_id, counter_key)
    gained = random.randint(*OFFSPRING_TEACH_EXP_RANGE)
    new_exp = off['exp'] + gained
    new_realm = off['realm_idx']
    while new_realm < OFFSPRING_REALM_CAP_IDX and new_exp >= REALMS[new_realm + 1]['exp']:
        new_realm += 1
    if new_realm != off['realm_idx']:
        _offspring_stage_notice(off, new_realm)
    run("UPDATE offspring SET exp=?, realm_idx=? WHERE id=?", (new_exp, new_realm, off_id))
    msg = f"仙人下凡,亲自教养{off['name']},见长 +{gained}"
    if new_realm > off['realm_idx']:
        msg += f",已至{REALMS[new_realm]['name']}"
    flash(msg, 'ok')
    return redirect(url_for('immortal_detail', char_id=char_id))

@app.route('/immortal/<int:char_id>/mail/<int:target_id>', methods=['POST'])
@login_required
def immortal_mail(char_id, target_id):
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    if target_id not in {r['id'] for r in _immortal_relations(char_id)}:
        flash('对方与你已无尘缘可寄', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    body = request.form.get('body', '').strip()
    if not (1 <= len(body) <= 200):
        flash('信件内容需在1-200字之间', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    if get_daily_counter(char_id, 'immortal_mail') >= MAIL_DAILY_LIMIT:
        flash('今日已寄信多次,明日再来', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    # 飞升前遗留的行囊仍在,可顺带捎给在世至亲——绑定物品(宗门制式/唯一法宝/灵珠)一律不许带下凡
    attach_material_key = request.form.get('attach_material_key', '').strip()
    attach_material_qty = max(0, request.form.get('attach_material_qty', type=int) or 0)
    attach_equipment_key = request.form.get('attach_equipment_key', '').strip()
    attach_equipment_qty = max(0, request.form.get('attach_equipment_qty', type=int) or 0)
    if attach_material_key and (attach_material_key not in MATERIAL_LABELS or attach_material_key == 'lingzhu_bead'):
        attach_material_key = ''
        attach_material_qty = 0
    equip_tpl = EQUIPMENT_TEMPLATES_BY_KEY.get(attach_equipment_key)
    if attach_equipment_key and (not equip_tpl or equip_tpl.get('zone') in ('unique', 'sect')):
        attach_equipment_key = ''
        attach_equipment_qty = 0
    attachment = {}
    if attach_material_key and attach_material_qty > 0:
        if not _inventory_consume(char_id, 'material', attach_material_qty, attach_material_key):
            flash('这份材料你没有这么多', 'error')
            return redirect(url_for('immortal_detail', char_id=char_id))
        attachment['materials'] = {attach_material_key: attach_material_qty}
    if attach_equipment_key and attach_equipment_qty > 0:
        if not _inventory_consume(char_id, 'gear', attach_equipment_qty, attach_equipment_key):
            if attachment.get('materials'):
                for mk, mq in attachment['materials'].items():
                    _grant_material(char_id, mk, mq)
            flash('这件装备你没有这么多', 'error')
            return redirect(url_for('immortal_detail', char_id=char_id))
        attachment['equipment'] = {attach_equipment_key: attach_equipment_qty}
    if attachment:
        body = body + f"\n\n随信附上:{_reward_desc(attachment)}"
    bump_daily_counter(char_id, 'immortal_mail')
    send_player_mail(char, target_id, '仙人寄语', body, attachment=attachment or None)
    flash('信已寄出', 'ok')
    return redirect(url_for('immortal_detail', char_id=char_id))

@app.route('/immortal/<int:char_id>/gifts/<int:gift_id>/<response>', methods=['POST'])
@login_required
def immortal_gift_respond(char_id, gift_id, response):
    """赠礼阁在世那边一直能送(gift_send 没卡对方是否在世),这里补上飞升者查收/回应的入口,
    跟 gift_respond 同一套逻辑,只是鉴权换成 _immortal_char。"""
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    gift = q("SELECT * FROM bond_gifts WHERE id=? AND recipient_id=? AND status='pending'", (gift_id, char_id), one=True)
    if not gift or response not in ('accept', 'decline'):
        flash('这份礼物已被处理', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    if response == 'decline':
        run("UPDATE bond_gifts SET recipient_id=NULL,status='inventory',responded_ts=? WHERE id=?", (now_ts(), gift_id))
        flash('已婉言谢绝,礼物原样退回对方行囊', 'ok')
        return redirect(url_for('immortal_detail', char_id=char_id))
    active_bond = q("SELECT 1 FROM bonds WHERE id=? AND status='active' AND (char_a_id=? OR char_b_id=?)",
                    (gift['bond_id'], char_id, char_id), one=True)
    if not active_bond:
        run("UPDATE bond_gifts SET recipient_id=NULL,status='inventory',responded_ts=? WHERE id=?", (now_ts(), gift_id))
        flash('这段羁绊已经结束,礼物已原样退回', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    gain = (GIFT_TYPES[gift['gift_type']]['base_affinity'] + GIFT_RARITIES[gift['rarity_key']]['affinity_bonus'] +
            GIFT_TRAITS[gift['trait_key']]['affinity_bonus'])
    giver = q("SELECT name FROM characters WHERE id=?", (gift['maker_id'],), one=True)
    memory = f"{giver['name']}将「{gift['gift_name']}」寄至仙籍,{char['name']}遥遥收下,郑重收入珍藏。"
    run("UPDATE bond_gifts SET owner_id=?,status='cherished',responded_ts=? WHERE id=?", (char_id, now_ts(), gift_id))
    run("UPDATE bonds SET affinity=MIN(100,affinity+?) WHERE id=? AND status='active'", (gain, gift['bond_id']))
    run("""INSERT INTO bond_interactions(bond_id,actor_id,action_key,day,memory_text,affinity_gain,created_ts)
        VALUES(?,?,?,?,?,?,?)""", (gift['bond_id'], gift['maker_id'], 'gift', f'gift-{gift_id}', memory, gain, now_ts()))
    flash(f"你收下「{gift['gift_name']}」并纳入珍藏,双方默契+{gain}", 'ok')
    return redirect(url_for('immortal_detail', char_id=char_id))

@app.route('/immortal/<int:char_id>/graveyard/<int:dead_id>/sweep', methods=['POST'])
@login_required
def immortal_graveyard_sweep(char_id, dead_id):
    char = _immortal_char(char_id)
    if not char:
        flash('并无此位飞升前辈', 'error')
        return redirect(url_for('immortal_home'))
    dead = q("SELECT * FROM characters WHERE id=? AND deceased=1", (dead_id,), one=True)
    if not dead:
        flash('此人并未安葬于此', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    if get_daily_counter(char_id, 'immortal_graveyard_sweep') >= GRAVEYARD_SWEEP_DAILY_LIMIT:
        flash('今日已扫墓多次,该回天上歇息了', 'error')
        return redirect(url_for('immortal_detail', char_id=char_id))
    bump_daily_counter(char_id, 'immortal_graveyard_sweep')
    run("UPDATE characters SET incense_count=incense_count+1 WHERE id=?", (dead_id,))
    flash(f"仙人下凡,亲至{dead['name']}墓前,焚香追思片刻,又悄然离去", 'ok')
    return redirect(url_for('immortal_detail', char_id=char_id))

# ── 管理后台:首页统计 ────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin_home():
    stats = {
        'pending':    q("SELECT COUNT(*) c FROM users WHERE status='pending'", one=True)['c'],
        'approved':   q("SELECT COUNT(*) c FROM users WHERE status='approved' AND role='player'", one=True)['c'],
        'rejected':   q("SELECT COUNT(*) c FROM users WHERE status='rejected'", one=True)['c'],
        'characters': q("SELECT COUNT(*) c FROM characters", one=True)['c'],
        'peaks':      q("SELECT COUNT(*) c FROM peaks", one=True)['c'],
        'elders':     q("SELECT COUNT(*) c FROM characters WHERE rank_tier=5", one=True)['c'],
    }
    return render_template('admin/home.html', stats=stats)

# ── 管理后台:待审核账号队列 ───────────────────────────────────────────────────────

@app.route('/admin/pending_users')
@admin_required
def admin_pending_users():
    status_filter = request.args.get('status', 'pending')
    if status_filter == 'all':
        users = q("SELECT * FROM users WHERE role='player' ORDER BY created_ts DESC")
    else:
        users = q("SELECT * FROM users WHERE role='player' AND status=? ORDER BY created_ts DESC", (status_filter,))
    return render_template('admin/pending_users.html', users=users, status_filter=status_filter)

@app.route('/admin/users/<int:uid>/approve', methods=['POST'])
@admin_required
def admin_approve_user(uid):
    run("UPDATE users SET status='approved' WHERE id=?", (uid,))
    log_admin('approve_user', 'user', uid)
    return redirect(url_for('admin_pending_users'))

@app.route('/admin/users/<int:uid>/reject', methods=['POST'])
@admin_required
def admin_reject_user(uid):
    run("UPDATE users SET status='rejected' WHERE id=?", (uid,))
    log_admin('reject_user', 'user', uid)
    return redirect(url_for('admin_pending_users'))

@app.route('/admin/users/<int:uid>/reset_password', methods=['POST'])
@admin_required
def admin_reset_password(uid):
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    status_filter = request.form.get('status_filter', 'all')
    if not user:
        flash('账号不存在', 'error')
        return redirect(url_for('admin_pending_users', status=status_filter))
    new_password = request.form.get('new_password', '').strip()
    if not (6 <= len(new_password) <= 40):
        flash('新密码长度需在 6-40 位之间', 'error')
        return redirect(url_for('admin_pending_users', status=status_filter))
    run("UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(new_password, method='pbkdf2:sha256'), uid))
    log_admin('reset_password', 'user', uid, f"username={user['username']}")
    flash(f"已为{user['username']}重置密码", 'ok')
    return redirect(url_for('admin_pending_users', status=status_filter))

@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    user = q("SELECT * FROM users WHERE id=?", (uid,), one=True)
    status_filter = request.form.get('status_filter', 'all')
    if not user:
        flash('账号不存在', 'error')
        return redirect(url_for('admin_pending_users', status=status_filter))
    if user['role'] != 'player':
        flash('不可删除管理员账号', 'error')
        return redirect(url_for('admin_pending_users', status=status_filter))
    if user['status'] == 'deleted':
        flash('该账号已被删除', 'error')
        return redirect(url_for('admin_pending_users', status=status_filter))
    # 软删除:账号无法再登录、用户名腾出可重新注册,但角色数据保留(避免连带删除牵扯到的
    # 邮件/羁绊/子嗣等其他玩家的数据,真出问题也能从数据库备份里找回)
    freed_username = f"{user['username']}_deleted_{now_ts()}"
    run("UPDATE users SET username=?, password_hash=?, status='deleted' WHERE id=?",
        (freed_username, generate_password_hash(os.urandom(16).hex(), method='pbkdf2:sha256'), uid))
    log_admin('delete_user', 'user', uid, f"original_username={user['username']}")
    flash(f"已删除账号{user['username']}(角色数据仍保留,原用户名可被重新注册)", 'ok')
    return redirect(url_for('admin_pending_users', status=status_filter))

# ── 管理后台:角色列表 / 详情编辑 ─────────────────────────────────────────────────

# ── 管理后台:批量发奖(勾选角色→站内信附件发放) ────────────────────────────────────

@app.route('/admin/mail_reward', methods=['GET', 'POST'])
@admin_required
def admin_mail_reward():
    if request.method == 'POST':
        char_ids = [int(x) for x in request.form.getlist('char_ids') if x.isdigit()]
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        reward = {}
        for key in _REWARD_FIELDS:
            val = request.form.get(key, type=int) or 0
            if val:
                reward[key] = val
        materials = {}
        for tier in MATERIAL_TIERS:
            val = request.form.get(f'material_{tier}', type=int) or 0
            if val:
                materials[tier] = val
        equipment_key = request.form.get('equipment_key', '').strip()
        equipment_qty = request.form.get('equipment_qty', type=int) or 0
        pet_key = request.form.get('pet_key', '').strip()
        pet_name = request.form.get('pet_name', '').strip() or None
        if equipment_key and equipment_key not in EQUIPMENT_TEMPLATES_BY_KEY:
            equipment_key = ''
        if pet_key and pet_key not in PET_TYPES:
            pet_key = ''
        if not char_ids or not subject:
            flash('请至少选择一名收信人并填写标题', 'error')
            return redirect(url_for('admin_mail_reward'))
        item_lines = []
        if materials:
            item_lines.append('、'.join(f"{MATERIAL_LABELS[k]}×{v}" for k, v in materials.items()))
        if equipment_key and equipment_qty > 0:
            item_lines.append(f"{EQUIPMENT_TEMPLATES_BY_KEY[equipment_key]['label']}×{equipment_qty}")
        if pet_key:
            item_lines.append(f"灵宠·{PET_TYPES[pet_key]['label']}")
        item_desc = '；'.join(item_lines)
        full_body = body + (f"\n\n随信附上:{item_desc}" if item_desc else '')
        for char_id in char_ids:
            send_system_mail(char_id, subject, full_body, attachment=reward or None, from_label='掌门发放')
            for tier, qty in materials.items():
                _grant_material(char_id, tier, qty)
            if equipment_key and equipment_qty > 0:
                _inventory_grant(char_id, 'gear', equipment_qty, equipment_key)
            if pet_key:
                run("""INSERT INTO character_pets (char_id,pet_key,pet_name,level,exp,bound_ts,location)
                       VALUES (?,?,?,1,0,?,'roster')""", (char_id, pet_key, pet_name, now_ts()))
        log_admin('mail_reward', 'characters', None,
                  f"{subject}·{len(char_ids)}人·{_reward_desc(reward) if reward else '无附件'}"
                  f"{('·' + item_desc) if item_desc else ''}")
        flash(f'已发送给{len(char_ids)}人', 'ok')
        return redirect(url_for('admin_mail_reward'))
    chars = q("""SELECT characters.* FROM characters
                 WHERE ascended=0 AND deceased=0 AND is_npc=0
                 ORDER BY characters.join_seq ASC""")
    return render_template('admin/mail_reward.html', chars=chars, title_for=title_for,
                            reward_fields=_REWARD_FIELDS, reward_labels=_REWARD_LABELS,
                            material_tiers=MATERIAL_TIERS, material_labels=MATERIAL_LABELS,
                            equipment_templates=EQUIPMENT_TEMPLATES_BY_KEY, pet_types=PET_TYPES)

@app.route('/admin/characters')
@admin_required
def admin_characters():
    chars = q("""SELECT characters.*, users.username FROM characters
                 JOIN users ON users.id = characters.user_id
                 ORDER BY characters.created_ts DESC""")
    real_chars = q("SELECT id, name, gender, join_seq FROM characters WHERE is_npc=0 ORDER BY join_seq ASC")
    return render_template('admin/characters.html', chars=chars, rank_by_tier=rank_by_tier,
                            title_for=title_for, realm_by_index=realm_by_index, real_chars=real_chars)

@app.route('/admin/characters/swap_join_seq', methods=['POST'])
@admin_required
def admin_swap_join_seq():
    char_a = request.form.get('char_a', type=int)
    char_b = request.form.get('char_b', type=int)
    if not char_a or not char_b or char_a == char_b:
        flash('请选择两个不同的角色', 'error')
        return redirect(url_for('admin_characters'))
    a = q("SELECT id, name, join_seq FROM characters WHERE id=? AND is_npc=0", (char_a,), one=True)
    b = q("SELECT id, name, join_seq FROM characters WHERE id=? AND is_npc=0", (char_b,), one=True)
    if not a or not b:
        flash('角色不存在', 'error')
        return redirect(url_for('admin_characters'))
    run("UPDATE characters SET join_seq=? WHERE id=?", (b['join_seq'], a['id']))
    run("UPDATE characters SET join_seq=? WHERE id=?", (a['join_seq'], b['id']))
    log_admin('swap_join_seq', 'characters', None,
              f"{a['name']}({a['join_seq']})↔{b['name']}({b['join_seq']})")
    flash(f"已交换 {a['name']} 与 {b['name']} 的排名顺序", 'ok')
    return redirect(url_for('admin_characters'))

@app.route('/admin/characters/<int:char_id>', methods=['GET', 'POST'])
@admin_required
def admin_character_detail(char_id):
    char = q("SELECT characters.*, users.username FROM characters "
             "JOIN users ON users.id = characters.user_id WHERE characters.id=?", (char_id,), one=True)
    if not char:
        flash('角色不存在', 'error')
        return redirect(url_for('admin_characters'))

    if request.method == 'POST':
        gender = request.form.get('gender') if request.form.get('gender') in ('m', 'f') else char['gender']
        realm_idx = max(0, min(MAX_REALM_INDEX, request.form.get('realm_idx', type=int) or 0))
        exp = max(0, request.form.get('exp', type=int) or 0)
        rank_tier = max(0, min(len(RANKS) - 1, request.form.get('rank_tier', type=int) or 0))
        contribution = max(0, request.form.get('contribution', type=int) or 0)
        total_contribution = max(contribution, request.form.get('total_contribution', type=int) or 0)
        spirit_root = request.form.get('spirit_root') or None
        if spirit_root == 'heaven':
            spirit_root_elements = None  # 天灵根五行皆通,不绑定具体属性,勾选框对它无意义
        else:
            picked = [e for e in request.form.getlist('elements') if e in ELEMENT_ORDER]
            if not picked and spirit_root and spirit_root != char['spirit_root']:
                picked = roll_spirit_root_elements(spirit_root)  # 换了档位又没手动勾选,按新档位随机补齐
            spirit_root_elements = ','.join(sorted(picked, key=ELEMENT_ORDER.index)) if picked else None
        talent_key = request.form.get('talent_key') or None
        immortal_bone_key = request.form.get('immortal_bone_key') or None
        bonus_lifespan_years = max(0, request.form.get('bonus_lifespan_years', type=int) or 0)
        deceased = 1 if request.form.get('deceased') else 0
        ascended = 1 if request.form.get('ascended') else 0
        stamina = max(0, min(STAMINA_CAP, request.form.get('stamina', type=int) or 0))
        physique = max(0, request.form.get('physique', type=int) or 0)
        mind_state = max(0, min(100, request.form.get('mind_state', type=int) or 0))
        reputation = max(0, request.form.get('reputation', type=int) or 0)
        lingshi = max(0, request.form.get('lingshi', type=int) or 0)
        equipped_weapon_key = request.form.get('equipped_weapon_key', '').strip() or None
        equipped_armor_key = request.form.get('equipped_armor_key', '').strip() or None
        equipped_accessory_key = request.form.get('equipped_accessory_key', '').strip() or None
        run("UPDATE characters SET gender=?, realm_idx=?, exp=?, rank_tier=?, contribution=?, total_contribution=?, "
            "spirit_root=?, spirit_root_elements=?, talent_key=?, immortal_bone_key=?, bonus_lifespan_years=?, deceased=?, ascended=?, "
            "stamina=?, physique=?, mind_state=?, reputation=?, lingshi=?, "
            "equipped_weapon_key=?, equipped_armor_key=?, equipped_accessory_key=? WHERE id=?",
            (gender, realm_idx, exp, rank_tier, contribution, total_contribution,
             spirit_root, spirit_root_elements, talent_key, immortal_bone_key, bonus_lifespan_years, deceased, ascended,
             stamina, physique, mind_state, reputation, lingshi,
             equipped_weapon_key, equipped_armor_key, equipped_accessory_key, char_id))
        check_achievements(char_id)
        log_admin('edit_character', 'character', char_id,
                  f"realm={realm_idx} exp={exp} rank={rank_tier} contrib={contribution} lingshi={lingshi}")
        flash('已保存', 'ok')
        return redirect(url_for('admin_character_detail', char_id=char_id))

    materials = q("SELECT * FROM character_materials WHERE char_id=? ORDER BY material_key", (char_id,))
    equipment = q("SELECT * FROM character_equipment WHERE char_id=? ORDER BY item_key", (char_id,))
    pets = q("SELECT * FROM character_pets WHERE char_id=? ORDER BY id", (char_id,))
    current_elements = (char['spirit_root_elements'] or '').split(',')
    pastlife_result = PAST_LIFE_FIGURES.get(char['pastlife_key']) if char['pastlife_key'] else None
    pastlife_path = json.loads(char['pastlife_path_json'] or '[]')
    pastlife_path_labels = [PASTLIFE_TAG_LABELS[PASTLIFE_DIMENSIONS[i]][v] for i, v in enumerate(pastlife_path)]
    pastlife_stage = PASTLIFE_STAGES[pastlife_stage_index(len(pastlife_path))] if not pastlife_result else None
    return render_template('admin/character_detail.html', char=char, realms=REALMS, ranks=RANKS,
                            title_for=title_for, spirit_roots=SPIRIT_ROOTS, spirit_root_order=SPIRIT_ROOT_ORDER,
                            spirit_root_elements_label=spirit_root_elements_label,
                            ELEMENTS=ELEMENTS, ELEMENT_ORDER=ELEMENT_ORDER, current_elements=current_elements,
                            talents=TALENTS, immortal_bones=IMMORTAL_BONES,
                            materials=materials, equipment=equipment, pets=pets, pet_types=PET_TYPES,
                            pastlife_result=pastlife_result, pastlife_path_labels=pastlife_path_labels,
                            pastlife_stage=pastlife_stage, pastlife_progress=char['pastlife_progress'],
                            pastlife_threshold=PASTLIFE_STAGE_THRESHOLD)

@app.route('/admin/characters/<int:char_id>/material', methods=['POST'])
@admin_required
def admin_character_material(char_id):
    material_key = request.form.get('material_key', '').strip()
    qty = request.form.get('qty', type=int)
    if not material_key or qty is None:
        flash('材料key和数量都要填', 'error')
        return redirect(url_for('admin_character_detail', char_id=char_id))
    if qty <= 0:
        run("DELETE FROM character_materials WHERE char_id=? AND material_key=?", (char_id, material_key))
    else:
        run("""INSERT INTO character_materials (char_id,material_key,qty) VALUES (?,?,?)
               ON CONFLICT(char_id,material_key) DO UPDATE SET qty=excluded.qty""",
            (char_id, material_key, qty))
    log_admin('set_material', 'character', char_id, f"{material_key}={qty}")
    flash('已保存', 'ok')
    return redirect(url_for('admin_character_detail', char_id=char_id))

@app.route('/admin/characters/<int:char_id>/equipment_item', methods=['POST'])
@admin_required
def admin_character_equipment_item(char_id):
    item_key = request.form.get('item_key', '').strip()
    qty = request.form.get('qty', type=int)
    if not item_key or qty is None:
        flash('装备key和数量都要填', 'error')
        return redirect(url_for('admin_character_detail', char_id=char_id))
    if qty <= 0:
        run("DELETE FROM character_equipment WHERE char_id=? AND item_key=?", (char_id, item_key))
    else:
        run("""INSERT INTO character_equipment (char_id,item_key,qty) VALUES (?,?,?)
               ON CONFLICT(char_id,item_key) DO UPDATE SET qty=excluded.qty""",
            (char_id, item_key, qty))
    log_admin('set_equipment', 'character', char_id, f"{item_key}={qty}")
    flash('已保存', 'ok')
    return redirect(url_for('admin_character_detail', char_id=char_id))

@app.route('/admin/characters/<int:char_id>/pet', methods=['POST'])
@admin_required
def admin_character_pet_grant(char_id):
    pet_key = request.form.get('pet_key', '').strip()
    name = request.form.get('name', '').strip() or None
    if pet_key not in PET_TYPES:
        flash('灵宠物种key不存在', 'error')
        return redirect(url_for('admin_character_detail', char_id=char_id))
    char = q("SELECT name FROM characters WHERE id=?", (char_id,), one=True)
    run("""INSERT INTO character_pets (char_id,pet_key,pet_name,level,exp,bound_ts,location)
           VALUES (?,?,?,1,0,?,'roster')""", (char_id, pet_key, name, now_ts()))
    log_admin('grant_pet', 'character', char_id, f"{pet_key} name={name}")
    flash('已发放灵宠', 'ok')
    return redirect(url_for('admin_character_detail', char_id=char_id))

@app.route('/admin/characters/<int:char_id>/pet/<int:pet_id>/delete', methods=['POST'])
@admin_required
def admin_character_pet_delete(char_id, pet_id):
    run("DELETE FROM character_pets WHERE id=? AND char_id=?", (pet_id, char_id))
    run("UPDATE characters SET equipped_pet_id=NULL WHERE id=? AND equipped_pet_id=?", (char_id, pet_id))
    log_admin('delete_pet', 'character', char_id, f"pet_id={pet_id}")
    flash('已删除该灵宠', 'ok')
    return redirect(url_for('admin_character_detail', char_id=char_id))

# ── 管理后台:邀请码 / 礼包码 / 操作日志 ─────────────────────────────────────────

@app.route('/admin/invite_codes', methods=['GET', 'POST'])
@admin_required
def admin_invite_codes():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        max_uses = request.form.get('max_uses', type=int) or 1
        expire_days = request.form.get('expire_days', type=int) or 0
        expires_ts = now_ts() + expire_days * 86400 if expire_days else 0
        if code:
            run("INSERT INTO invite_codes (code,max_uses,used_count,expires_ts,created_ts) VALUES (?,?,0,?,?)",
                (code, max_uses, expires_ts, now_ts()))
            log_admin('create_invite_code', 'invite_code', None, code)
        return redirect(url_for('admin_invite_codes'))
    codes = q("SELECT * FROM invite_codes ORDER BY created_ts DESC")
    return render_template('admin/invite_codes.html', codes=codes)

@app.route('/admin/gift_codes', methods=['GET', 'POST'])
@admin_required
def admin_gift_codes():
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        exp = request.form.get('exp', type=int) or 0
        contribution = request.form.get('contribution', type=int) or 0
        lifespan_years = request.form.get('lifespan_years', type=int) or 0
        max_uses = request.form.get('max_uses', type=int) or 1
        expire_days = request.form.get('expire_days', type=int) or 0
        expires_ts = now_ts() + expire_days * 86400 if expire_days else 0
        if code:
            run("INSERT INTO gift_codes (code,reward_json,max_uses,used_count,expires_ts,created_ts) "
                "VALUES (?,?,?,0,?,?)",
                (code, json.dumps({'exp': exp, 'contribution': contribution, 'lifespan_years': lifespan_years}),
                 max_uses, expires_ts, now_ts()))
            log_admin('create_gift_code', 'gift_code', None, code)
        return redirect(url_for('admin_gift_codes'))
    codes = q("SELECT * FROM gift_codes ORDER BY created_ts DESC")
    return render_template('admin/gift_codes.html', codes=codes)

@app.route('/admin/logs')
@admin_required
def admin_logs_page():
    logs = q("""SELECT admin_logs.*, users.username admin_name FROM admin_logs
                LEFT JOIN users ON users.id = admin_logs.admin_id
                ORDER BY admin_logs.created_ts DESC LIMIT 200""")
    return render_template('admin/logs.html', logs=logs)

# ── 管理后台:宗门配置(掌门继任定时事件) ─────────────────────────────────────────

@app.route('/admin/sect_config', methods=['GET', 'POST'])
@admin_required
def admin_sect_config():
    if request.method == 'POST':
        npc_leader_name = request.form.get('npc_leader_name', '').strip() or '沈天铭'
        target_str = request.form.get('succession_target_ts', '').strip()
        succession_target_ts = int(target_str) if target_str.isdigit() else now_ts()
        run("UPDATE sect_config SET npc_leader_name=?, succession_target_ts=? WHERE id=1",
            (npc_leader_name, succession_target_ts))
        log_admin('edit_sect_config', 'sect_config', 1, f"target_ts={succession_target_ts}")
        flash('已保存', 'ok')
        return redirect(url_for('admin_sect_config'))
    cfg = q("SELECT * FROM sect_config WHERE id=1", one=True)
    leader = current_leader()
    peaks = q("""SELECT peaks.*, elder.name elder_name, elder.is_npc elder_is_npc FROM peaks
                 LEFT JOIN characters elder ON elder.id = peaks.elder_id
                 ORDER BY peaks.is_leader DESC, peaks.id""")
    sect_year = game_year_of(now_ts(), cfg['founded_ts'])
    return render_template('admin/sect_config.html', cfg=cfg, leader=leader, peaks=peaks, sect_year=sect_year)

@app.route('/admin/sect_config/trigger_succession', methods=['POST'])
@admin_required
def admin_trigger_succession():
    """掌门继任已改为长老主动申请制,这里只负责提前打开申请窗口(不再自动选人)。"""
    run("UPDATE sect_config SET succession_target_ts=? WHERE id=1", (now_ts(),))
    log_admin('trigger_succession', 'sect_config', 1, '手动开放掌门申请窗口')
    flash('已立即开放掌门申请窗口,长老可自行前往「诸峰」页面申请继任', 'ok')
    return redirect(url_for('admin_sect_config'))

@app.route('/admin/sect_config/trigger_gossip', methods=['POST'])
@admin_required
def admin_trigger_gossip():
    ok = sect_gossip_fire()
    log_admin('trigger_gossip', 'sect_config', 1, f"result={ok}")
    flash('已生成一条宗门闲话' if ok else '在世的非NPC弟子不足2人,无法生成', 'ok' if ok else 'error')
    return redirect(url_for('admin_sect_config'))

@app.route('/admin/sect_config/ascend_leader', methods=['POST'])
@admin_required
def admin_ascend_leader():
    ok = ascend_leader()
    flash('已令现任掌门飞升离宗' if ok else '当前掌门峰无人在位,无法操作', 'ok' if ok else 'error')
    return redirect(url_for('admin_sect_config'))

@app.route('/admin/sect_config/trigger_lifespan', methods=['POST'])
@admin_required
def admin_trigger_lifespan():
    lifespan_tick()
    log_admin('trigger_lifespan_check', 'sect_config', 1)
    flash('寿元检查已执行', 'ok')
    return redirect(url_for('admin_sect_config'))

# ── 危险操作专区:整服重置 ───────────────────────────────────────────────────────

@app.route('/admin/danger_zone', methods=['GET', 'POST'])
@admin_required
def admin_danger_zone():
    if request.method == 'POST':
        confirm = request.form.get('confirm', '').strip()
        if confirm != RESET_CONFIRM_PHRASE:
            flash(f'确认文字不匹配,请原样输入「{RESET_CONFIRM_PHRASE}」', 'error')
            return redirect(url_for('admin_danger_zone'))
        backup_name = reset_game_to_initial_state(S.get('uname', 'unknown'))
        S.clear()
        flash(f'已重置为初始状态(所有玩家/角色/记录已清空)。重置前的数据已备份为 backups/{backup_name},请重新登录', 'ok')
        return redirect(url_for('login'))
    return render_template('admin/danger_zone.html', confirm_phrase=RESET_CONFIRM_PHRASE)

def _spawn_npc_elder(peak, profile):
    """在指定(空缺)长老峰上补一名NPC长老,复用统一的NPC账号。"""
    npc_user = q("SELECT id FROM users WHERE username=?", (NPC_ELDER_USERNAME,), one=True)
    if npc_user:
        npc_user_id = npc_user['id']
    else:
        run("INSERT INTO users (username,password_hash,qq,role,status,created_ts) VALUES (?,?,?,?,?,?)",
            (NPC_ELDER_USERNAME, generate_password_hash(os.urandom(16).hex(), method='pbkdf2:sha256'),
             '00000000', 'npc', 'approved', now_ts()))
        npc_user_id = q("SELECT id FROM users WHERE username=?", (NPC_ELDER_USERNAME,), one=True)['id']
    elder_rank = RANKS[5]
    cur = run(
        "INSERT INTO characters (user_id,name,gender,bio,realm_idx,exp,rank_tier,join_seq,peak_id,"
        "contribution,total_contribution,reputation,is_npc,created_ts) "
        "VALUES (?,?,?,?,?,?,5,?,?,?,?,?,1,?)",
        (npc_user_id, profile['name'], profile['gender'], profile['bio'], profile['realm_idx'],
         REALMS[profile['realm_idx']]['exp'], 0, peak['id'],
         elder_rank['contribution_req'], elder_rank['contribution_req'], elder_rank['reputation_req'],
         now_ts()))
    run("UPDATE peaks SET elder_id=? WHERE id=?", (cur.lastrowid, peak['id']))
    return cur.lastrowid

@app.route('/admin/sect_config/spawn_npc_elder/<int:peak_id>', methods=['POST'])
@admin_required
def admin_spawn_npc_elder(peak_id):
    peak = q("SELECT * FROM peaks WHERE id=?", (peak_id,), one=True)
    if not peak or peak['is_leader']:
        flash('掌门峰不支持补NPC长老', 'error')
        return redirect(url_for('admin_sect_config'))
    if peak['elder_id']:
        flash(f"{peak['name']}长老之位已有人在任,无需补位", 'error')
        return redirect(url_for('admin_sect_config'))
    profile = pick_npc_elder_profile(peak['name'])
    if not profile:
        flash(f"{peak['name']}没有配置NPC候选人选", 'error')
        return redirect(url_for('admin_sect_config'))
    _spawn_npc_elder(peak, profile)
    log_admin('spawn_npc_elder', 'peak', peak_id, f"{peak['name']} <- {profile['name']}")
    flash(f"已为{peak['name']}补入NPC长老{profile['name']}", 'ok')
    return redirect(url_for('admin_sect_config'))

# ── 管理后台:化身登录(排障用) ────────────────────────────────────────────────────

@app.route('/admin/impersonate/<int:char_id>')
@admin_required
def admin_impersonate(char_id):
    char = q("SELECT characters.*, users.id user_id, users.username FROM characters "
             "JOIN users ON users.id = characters.user_id WHERE characters.id=?", (char_id,), one=True)
    if not char:
        flash('角色不存在', 'error')
        return redirect(url_for('admin_characters'))
    log_admin('impersonate', 'character', char_id, char['username'])
    S['real_admin_uid'] = S['uid']
    S['uid'] = char['user_id']; S['uname'] = char['username']; S['role'] = 'player'
    return redirect(url_for('home'))

@app.route('/admin/unimpersonate')
def admin_unimpersonate():
    admin_uid = S.get('real_admin_uid')
    if not admin_uid:
        return redirect(url_for('login'))
    admin_user = q("SELECT * FROM users WHERE id=?", (admin_uid,), one=True)
    S.pop('real_admin_uid', None)
    S['uid'] = admin_user['id']; S['uname'] = admin_user['username']; S['role'] = 'admin'
    return redirect(url_for('admin_home'))
