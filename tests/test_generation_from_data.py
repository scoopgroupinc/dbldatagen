import logging
import ast
import re
import pytest

import pyspark.sql as ssql

import dbldatagen as dg

spark = dg.SparkSingleton.getLocalInstance("unit tests")


@pytest.fixture(scope="class")
def setupLogging():
    FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=FORMAT)


class TestGenerationFromData:
    SMALL_ROW_COUNT = 10000

    @pytest.fixture
    def testLogger(self):
        logger = logging.getLogger(__name__)
        return logger

    @pytest.fixture
    def generation_spec(self):

        country_codes = [
            "CN", "US", "FR", "CA", "IN", "JM", "IE", "PK", "GB", "IL", "AU",
            "SG", "ES", "GE", "MX", "ET", "SA", "LB", "NL",
        ]
        country_weights = [
            1300, 365, 67, 38, 1300, 3, 7, 212, 67, 9, 25, 6, 47, 83,
            126, 109, 58, 8, 17,
        ]

        eurozone_countries = ["Austria", "Belgium", "Cyprus", "Estonia", "Finland", "France", "Germany", "Greece",
                              "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands",
                              "Portugal", "Slovakia", "Slovenia", "Spain"
                              ]

        spec = (
            dg.DataGenerator(sparkSession=spark, name='test_generator',
                             rows=self.SMALL_ROW_COUNT, seedMethod='hash_fieldname')
            .withColumn('asin', 'string', template=r"adddd", random=True)
            .withColumn('brand', 'string', template=r"\w|\w \w \w|\w \w \w")
            .withColumn('helpful', 'array<bigint>', expr="array(floor(rand()*100), floor(rand()*100))")
            .withColumn('img', 'string', expr="concat('http://www.acme.com/downloads/images/', asin, '.png')",
                        baseColumn="asin")
            .withColumn('price', 'double', min=1.0, max=999.0, random=True, step=0.01)
            .withColumn('rating', 'double', values=[1.0, 2, 0, 3.0, 4.0, 5.0], random=True)
            .withColumn('review', 'string', text=dg.ILText((1, 3), (1, 4), (3, 8)), random=True, percentNulls=0.1)
            .withColumn('time', 'bigint', expr="now()", percentNulls=0.1)
            .withColumn('title', 'string', template=r"\w|\w \w \w|\w \w \w|\w \w \w \w", random=True)
            .withColumn('user', 'string', expr="hex(abs(hash(id)))")
            .withColumn("event_ts", "timestamp", begin="2020-01-01 01:00:00",
                        end="2020-12-31 23:59:00",
                        interval="1 minute", random=True)
            .withColumn("r_value", "float", expr="floor(rand() * 350) * (86400 + 3600)",
                        numColumns=(2, 4), structType="array")
            .withColumn("tf_flag", "boolean", expr="id % 2 = 1")
            .withColumn("short_value", "short", max=32767, percentNulls=0.1)
            .withColumn("string_values", "string", values=["one", "two", "three"])
            .withColumn("country_codes", "string", values=country_codes, weights=country_weights)
            .withColumn("euro_countries", "string", values=eurozone_countries)
            .withColumn("int_value", "int", min=100, max=200, percentNulls=0.1)
            .withColumn("byte_value", "tinyint", max=127)
            .withColumn("decimal_value", "decimal(10,2)", max=1000000)
            .withColumn("decimal_value", "decimal(10,2)", max=1000000)
            .withColumn("date_value", "date", expr="current_date()", random=True)
            .withColumn("binary_value", "binary", expr="cast('spark' as binary)", random=True)

        )
        return spec

    def test_code_generation1(self, generation_spec, setupLogging):
        df_source_data = generation_spec.build()
        df_source_data.show()

        analyzer = dg.DataAnalyzer(sparkSession=spark, df=df_source_data)

        generatedCode = analyzer.scriptDataGeneratorFromData()

        for fld in df_source_data.schema:
            assert f"withColumn('{fld.name}'" in generatedCode

        # check generated code for syntax errors
        ast_tree = ast.parse(generatedCode)
        assert ast_tree is not None

    def test_code_generation_from_schema(self, generation_spec, setupLogging):
        df_source_data = generation_spec.build()
        generatedCode = dg.DataAnalyzer.scriptDataGeneratorFromSchema(df_source_data.schema)

        for fld in df_source_data.schema:
            assert f"withColumn('{fld.name}'" in generatedCode

        # check generated code for syntax errors
        ast_tree = ast.parse(generatedCode)
        assert ast_tree is not None

    def test_summarize(self, testLogger, generation_spec):
        testLogger.info("Building test data")

        df_source_data = generation_spec.build()

        testLogger.info("Creating data analyzer")

        analyzer = dg.DataAnalyzer(sparkSession=spark, df=df_source_data)

        testLogger.info("Summarizing data analyzer results")
        analyzer.summarize()

    def test_summarize_to_df(self, generation_spec, testLogger):
        testLogger.info("Building test data")

        df_source_data = generation_spec.build()

        testLogger.info("Creating data analyzer")

        analyzer = dg.DataAnalyzer(sparkSession=spark, df=df_source_data)

        testLogger.info("Summarizing data analyzer results")
        df = analyzer.summarizeToDF()

        #df.show()

        df_source_data.where("title is null or length(title) = 0").show()

    @pytest.mark.parametrize("sampleString, expectedMatch",
                             [("0234", "digits"),
                              ("http://www.yahoo.com", "url"),
                              ("http://www.yahoo.com/test.png", "image_url"),
                              ("info+new_account@databrickslabs.com", "email_uncommon"),
                              ("abcdefg", "alpha_lower"),
                              ("ABCDEFG", "alpha_upper"),
                              ("A09", "alphanumeric"),
                              ("this is a test ", "free_text"),
                              ("test_function", "identifier"),
                              ("10.0.0.1", "ip_addr")
                              ])
    def test_match_patterns(self, sampleString, expectedMatch, generation_spec):
        df_source_data = generation_spec.build()

        analyzer = dg.DataAnalyzer(sparkSession=spark, df=df_source_data)

        pattern_match_result = ""
        for k, v in analyzer._regex_patterns.items():
            pattern = f"^{v}$"

            if re.match(pattern, sampleString) is not None:
                pattern_match_result = k
                break

        assert pattern_match_result == expectedMatch, f"expected match to be {expectedMatch}"

    def test_source_data_property(self, generation_spec):
        df_source_data = generation_spec.build()
        analyzer = dg.DataAnalyzer(sparkSession=spark, df=df_source_data, maxRows=1000)

        count_rows = analyzer.sourceSampleDf.count()
        print(count_rows)
        assert abs(count_rows - 1000) < 100, "expected count to be close to 1000"

