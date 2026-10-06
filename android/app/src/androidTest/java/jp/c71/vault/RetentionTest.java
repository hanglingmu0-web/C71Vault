package jp.c71.vault;
import org.junit.*;
import org.json.*;
import java.time.*;
import java.util.*;
import static org.junit.Assert.*;

public class RetentionTest {
    final ZoneId zone=ZoneId.of("Asia/Tokyo");
    final LocalDate today=LocalDate.of(2026,9,29);
    long now(){return today.atTime(12,0).atZone(zone).toInstant().toEpochMilli();}
    JSONObject item(int id,int days,int hour,String series,boolean important)throws Exception{
        return new JSONObject().put("id",String.format("%032x",id)).put("stored_at",today.minusDays(days).atTime(hour,0).atZone(zone).toInstant().toEpochMilli()).put("series",series).put("important",important);
    }
    Set<String> candidates(JSONObject... items)throws Exception{JSONArray a=new JSONArray();for(JSONObject x:items)a.put(x);JSONArray p=Retention.candidates(a,now(),zone);Set<String> ids=new HashSet<>();for(int i=0;i<p.length();i++)ids.add(p.getJSONObject(i).getString("id"));return ids;}
    final String series="a".repeat(32);
    @Test public void allLast30DaysAndFutureAreRetained()throws Exception{assertTrue(candidates(item(1,0,1,series,false),item(2,29,1,series,false),item(3,29,2,series,false),item(4,-2,1,series,false)).isEmpty());}
    @Test public void days31to180RetainLatestPerDay()throws Exception{JSONObject old=item(1,30,1,series,false);assertEquals(Set.of(old.getString("id")),candidates(old,item(2,30,2,series,false),item(3,179,1,series,false)));}
    @Test public void differentSourcesNeverCompete()throws Exception{assertTrue(candidates(item(1,70,1,series,false),item(2,70,2,"b".repeat(32),false)).isEmpty());}
    @Test public void weeklyBucketsStartMonday()throws Exception{
        // 2026-03-02 Monday / 03-03 Tuesday, both in weekly retention range.
        int mon=(int)java.time.temporal.ChronoUnit.DAYS.between(LocalDate.of(2026,3,2),today);
        JSONObject older=item(1,mon,10,series,false);assertEquals(Set.of(older.getString("id")),candidates(older,item(2,mon-1,10,series,false)));
    }
    @Test public void annualBoundaryAndMonthlyBucket()throws Exception{JSONObject older=item(1,366,1,series,false);assertEquals(Set.of(older.getString("id")),candidates(older,item(2,365,1,series,false)));}
    @Test public void importantDoesNotRemoveOtherLatestRepresentative()throws Exception{assertTrue(candidates(item(1,60,1,series,true),item(2,60,2,series,false)).isEmpty());}
    @Test public void newestAndUnknownLegacyAreRetained()throws Exception{assertTrue(candidates(item(1,700,1,series,false),item(2,701,1,"",false),item(3,701,2,"",false)).isEmpty());}
    @Test public void exactly15PercentIsNotBelowThreshold(){assertFalse(Retention.needsAttention(15,100,15));assertTrue(Retention.needsAttention(14,100,15));}
}
