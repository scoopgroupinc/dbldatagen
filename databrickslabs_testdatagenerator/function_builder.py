# See the License for the specific language governing permissions and
# limitations under the License.
#
import itertools

from pyspark.sql.types import StringType, DateType, TimestampType


class ColumnGeneratorBuilder:
    """ Helper class to build functional column generators of specific forms"""

    @classmethod
    def _mk_list(cls, x):
        return [x] if type(x) is not list else x

    @classmethod
    def _last_element(cls, x):
        return x[-1] if type(x) is list else x

    @classmethod
    def mk_cdf_probabilities(cls, weights):
        """ make cumulative distribution function probabilities for each value in values list

        a cumulative distribution function for discrete values can uses
        a  table of cumulative probabilities to evaluate different expressions
        based on the cumulative  probability of each value occurring

        The probabilities can be computed from the weights using the code
           ``weight_interval = 1.0 / total_weights
           probs = [x * weight_interval for x in weights]
           return reduce((lambda x, y: cls._mk_list(x) + [cls._last_element(x) + y]), probs)``

        but Python provides built-in methods (itertools.accumulate) to compute the accumulated weights
        and dividing each resulting accumulated weight by the sum of the total weights will give the cumulative
        probabilities.

        For large data sets (relative to number of values), tests verify that the resulting distribution is
        within 10% of the expected distribution when using Spark SQL Rand() as a uniform random number generator.
        In testing, test data sets of size 3000 * number_of_values rows produce a distribution within 10% of expected ,
        while datasets of size 10,000 x `number of values` gives a repeated
        distribution within 5% of expected distribution.


        Example code to be generated (pseudo code):
            # given values value1 .. valueN, prob1 to probN
            # cdf_probabilities = [ prob1, prob1+prob2, ... prob1+prob2+prob3 .. +probN]
            # this will then be used as follows

            prob_occurrence = uniform_rand(0.0, 1.0)
            if prob_occurrence <= cdf_prob_value1 then value1
            elif prob_occurrence <= cdf_prob_value2 then value2
            ...
            prob_occurrence <= cdf_prob_valueN then valueN
            else valueN

        see:

        """
        total_weights = sum(weights)
        return list(map(lambda x: x / total_weights, itertools.accumulate(weights)))


    @classmethod
    def mk_expr_choices_fn(cls, values, weights, seed_column, datatype):
        """ build an expression of the form
          `` case
                when rnd_column <= weight1 then value1
                when rnd_column <= weight2 then value2
                ...
                when rnd_column <= weightN then  valueN
                else valueN
                end``

            based on computed probability distribution for values.

            In Python 3.6 onwards, we could use the choices function but this python version is not
            guaranteed on all Databricks distributions

        """
        cdf_probs = cls.mk_cdf_probabilities(weights)

        output = [" CASE "]

        conditions = zip(values, cdf_probs)
        output_type = type(datatype)

        for v, cdf in conditions:
            if output_type == StringType or output_type == DateType or output_type == TimestampType:
                output.append(" when {} <= {} then '{}' ".format(seed_column, cdf, v))
            else:
                output.append(" when {} <= {} then {} ".format(seed_column, cdf, v))

        output.append("else '{}'".format(values[-1]))
        output.append("end")

        retval = "\n".join(output)
        print(retval)
        print(datatype)

        return retval
