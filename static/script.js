document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('prediction-form');
    const btnPredict = document.getElementById('btn-predict');
    const btnRandom = document.getElementById('btn-fill-random');
    const loader = document.getElementById('loader');
    
    // Result Modal Elements
    const overlay = document.getElementById('result-overlay');
    const closeBtn = document.getElementById('close-result');
    const gaugeFill = document.getElementById('gauge-fill');
    const riskValueText = document.getElementById('risk-value');
    const predOutcome = document.getElementById('pred-outcome');
    const insightText = document.getElementById('insight-text');
    const stayProbText = document.getElementById('stay-prob');

    // ─── Dynamic Chart Loading via /charts API ──────────────────
    // Maps chart API key -> img element id
    const CHART_IMG_MAP = {
        attrition_distribution:  'img-attrition-distribution',
        categorical_countplots:  'img-categorical-countplots',
        numeric_boxplots:        'img-numeric-boxplots',
        correlation_matrix:      'img-correlation-matrix',
        roc_curves:              'img-roc-curves',
        confusion_matrices:      'img-confusion-matrices',
        feature_importance:      'img-feature-importance',
        shap_summary:            'img-shap-summary',
    };

    async function loadCharts() {
        try {
            const response = await fetch('/charts');
            if (!response.ok) return;
            const data = await response.json();
            const charts = data.charts || {};
            for (const [key, url] of Object.entries(charts)) {
                if (!url) continue;
                const imgId = CHART_IMG_MAP[key];
                if (imgId) {
                    const el = document.getElementById(imgId);
                    if (el) el.src = url;
                }
            }
        } catch (err) {
            console.warn('Could not load chart URLs from /charts API:', err);
            // Charts will fall back to the static /outputs/ src already set in HTML
        }
    }

    loadCharts();

    // ─── Handle Form Submit ─────────────────────────────────────
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Show loader, disable button
        loader.style.display = 'block';
        btnPredict.disabled = true;
        btnPredict.querySelector('span').style.opacity = '0.5';

        // Gather data
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        
        // Convert numbers
        const numericFields = [
            'Age', 'DailyRate', 'DistanceFromHome', 'Education', 'EnvironmentSatisfaction',
            'HourlyRate', 'JobInvolvement', 'JobLevel', 'JobSatisfaction', 'MonthlyIncome',
            'MonthlyRate', 'NumCompaniesWorked', 'PercentSalaryHike', 'PerformanceRating',
            'RelationshipSatisfaction', 'StockOptionLevel', 'TotalWorkingYears',
            'TrainingTimesLastYear', 'WorkLifeBalance', 'YearsAtCompany',
            'YearsInCurrentRole', 'YearsSinceLastPromotion', 'YearsWithCurrManager'
        ];
        
        numericFields.forEach(field => {
            if (data[field]) data[field] = parseInt(data[field], 10);
        });

        try {
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            if (!response.ok) {
                throw new Error('Prediction failed');
            }

            const result = await response.json();
            showResult(result);

        } catch (error) {
            alert('Error making prediction: ' + error.message);
        } finally {
            loader.style.display = 'none';
            btnPredict.disabled = false;
            btnPredict.querySelector('span').style.opacity = '1';
        }
    });

    function showResult(result) {
        const isLeave = result.prediction === 'Leave';
        const leaveProb = (result.leave_probability * 100).toFixed(1);
        const stayProb = (result.stay_probability * 100).toFixed(1);
        
        // Setup Modal UI
        predOutcome.textContent = result.prediction.toUpperCase();
        predOutcome.className = `badge ${isLeave ? 'leave' : 'stay'}`;
        
        riskValueText.textContent = 0; // Reset for animation
        
        if (isLeave) {
            insightText.innerHTML = `High risk detected. Model shows a <span style="color:var(--danger);font-weight:bold">${leaveProb}%</span> probability of leaving.`;
            gaugeFill.style.stroke = 'var(--danger)';
        } else {
            insightText.innerHTML = `Employee is likely to stay with a <span style="color:var(--success);font-weight:bold">${stayProb}%</span> probability.`;
            gaugeFill.style.stroke = 'var(--success)';
        }

        overlay.classList.remove('hidden');

        // Animate Gauge & Numbers
        setTimeout(() => {
            const riskValue = isLeave ? parseFloat(leaveProb) : parseFloat(stayProb);
            
            // Gauge animation
            // 125.6 is the stroke-dasharray (circumference of semi-circle)
            const offset = 125.6 - (125.6 * riskValue / 100);
            gaugeFill.style.strokeDashoffset = offset;
            
            // Number counter animation
            let current = 0;
            const step = riskValue / 30;
            const timer = setInterval(() => {
                current += step;
                if (current >= riskValue) {
                    current = riskValue;
                    clearInterval(timer);
                }
                riskValueText.textContent = current.toFixed(1);
            }, 30);
            
        }, 100);
    }

    closeBtn.addEventListener('click', () => {
        overlay.classList.add('hidden');
        setTimeout(() => {
            gaugeFill.style.strokeDashoffset = 125.6; // Reset
        }, 300);
    });

    // ─── Random Data Generator ──────────────────────────────────
    btnRandom.addEventListener('click', () => {
        const randomData = {
            Age: rnd(22, 60),
            Gender: rChoice(['Male', 'Female']),
            MaritalStatus: rChoice(['Single', 'Married', 'Divorced']),
            Education: rnd(1, 5),
            EducationField: rChoice(['Life Sciences', 'Medical', 'Marketing', 'Technical Degree', 'Other', 'Human Resources']),
            DistanceFromHome: rnd(1, 29),
            NumCompaniesWorked: rnd(0, 9),
            
            Department: rChoice(['Sales', 'Research & Development', 'Human Resources']),
            JobRole: rChoice(['Sales Executive', 'Research Scientist', 'Laboratory Technician', 'Manufacturing Director', 'Healthcare Representative', 'Manager', 'Sales Representative', 'Research Director', 'Human Resources']),
            JobLevel: rnd(1, 5),
            BusinessTravel: rChoice(['Travel_Rarely', 'Travel_Frequently', 'Non-Travel']),
            MonthlyIncome: rnd(2000, 19000),
            DailyRate: rnd(100, 1499),
            HourlyRate: rnd(30, 100),
            MonthlyRate: rnd(2000, 26999),
            PercentSalaryHike: rnd(11, 25),
            OverTime: rChoice(['Yes', 'No']),
            
            EnvironmentSatisfaction: rnd(1, 4),
            JobSatisfaction: rnd(1, 4),
            RelationshipSatisfaction: rnd(1, 4),
            JobInvolvement: rnd(1, 4),
            WorkLifeBalance: rnd(1, 4),
            PerformanceRating: rChoice([3, 4]),
            
            TotalWorkingYears: rnd(1, 40),
            YearsAtCompany: rnd(0, 20),
            YearsInCurrentRole: rnd(0, 15),
            YearsSinceLastPromotion: rnd(0, 15),
            YearsWithCurrManager: rnd(0, 15),
            TrainingTimesLastYear: rnd(0, 6),
            StockOptionLevel: rnd(0, 3)
        };
        
        // Validation rules to make data look realistic
        if (randomData.YearsAtCompany > randomData.TotalWorkingYears) randomData.TotalWorkingYears = randomData.YearsAtCompany + rnd(0, 5);
        if (randomData.YearsInCurrentRole > randomData.YearsAtCompany) randomData.YearsInCurrentRole = randomData.YearsAtCompany;
        if (randomData.YearsSinceLastPromotion > randomData.YearsAtCompany) randomData.YearsSinceLastPromotion = randomData.YearsAtCompany;
        if (randomData.YearsWithCurrManager > randomData.YearsAtCompany) randomData.YearsWithCurrManager = randomData.YearsAtCompany;
        if (randomData.Age - 18 < randomData.TotalWorkingYears) randomData.Age = 18 + randomData.TotalWorkingYears + rnd(0, 5);

        for (const [key, value] of Object.entries(randomData)) {
            const el = document.getElementById(key);
            if (el) el.value = value;
        }
        
        // Pulse effect to show it worked
        form.style.transform = 'scale(0.99)';
        setTimeout(() => {
            form.style.transform = 'scale(1)';
        }, 150);
    });

    // ─── Helpers ────────────────────────────────────────────────
    function rnd(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }
    
    function rChoice(arr) {
        return arr[Math.floor(Math.random() * arr.length)];
    }

    // ─── Tab Navigation ─────────────────────────────────────────
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });
});
