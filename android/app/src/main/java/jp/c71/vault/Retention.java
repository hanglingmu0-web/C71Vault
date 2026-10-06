package jp.c71.vault;

import java.time.*;
import java.time.temporal.TemporalAdjusters;
import java.util.*;
import org.json.*;

/** A preview only. This class never deletes data. Age is measured in local calendar days. */
final class Retention {
    static JSONArray candidates(JSONArray archives, long now, ZoneId zone) throws Exception {
        LocalDate today = Instant.ofEpochMilli(now).atZone(zone).toLocalDate();
        List<JSONObject> sorted = new ArrayList<>();
        for (int i=0; i<archives.length(); i++) sorted.add(archives.getJSONObject(i));
        sorted.sort(Comparator.<JSONObject>comparingLong(m -> m.optLong("stored_at")).reversed()
            .thenComparing(m -> m.optString("id")));
        Set<String> latest = new HashSet<>(), buckets = new HashSet<>();
        JSONArray result = new JSONArray();
        for (JSONObject m : sorted) {
            String series = m.optString("series");
            // Older versions have no stable source identity: do not guess and delete them.
            if (!series.matches("[0-9a-f]{32}")) continue;
            series = m.optString("folder","未分類") + ":" + series;
            boolean newest = latest.add(series);
            LocalDate day = Instant.ofEpochMilli(m.getLong("stored_at")).atZone(zone).toLocalDate();
            long age = java.time.temporal.ChronoUnit.DAYS.between(day, today);
            if (age < 30) continue;
            String bucket;
            if (age < 180) bucket = "day:" + day;
            else if (day.isAfter(today.minusYears(1)))
                bucket = "week:" + day.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY));
            else bucket = "month:" + YearMonth.from(day);
            boolean representative = buckets.add(series + ":" + bucket);
            if (!newest && !representative && !m.optBoolean("important", false)) result.put(m);
        }
        return result;
    }
    static boolean needsAttention(long available, long total, int percent) {
        return total > 0 && available / (double)total < percent / 100.0;
    }
}
