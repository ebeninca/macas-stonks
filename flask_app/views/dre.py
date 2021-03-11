"""
O objetivo aqui é montar a DRE igual do fundamentei, sem as limitações impostas,
como a API do statusinvest é aberta, então temos os dados, a dificuldade está em
transpor as colunas de anos em linhas

# TODO considerar Earnings Yield (EBIT/EV e L/P)
"""
from flask import Flask, Blueprint, render_template, current_app, request

import requests
import json
import logging
import locale
import math
import datetime

from forms.dreForm import DreForm

bpDre = Blueprint('dre', __name__)


@bpDre.route('/dre')
def index():
    # form = DreForm(request.form)
    return render_template('dre.jinja')


@bpDre.route('/dre/search', methods=['GET'])
def search():
    current_app.logger.info("### DRE ###")
    if request.args.get('q') is None:
        return json.dumps([]), 200, {'content-type': 'application/json'}

    resp = requests.get(
        "https://statusinvest.com.br/home/mainsearchquery?q=" + request.args.get('q'))

    companyInfoJson = json.loads(resp.text)
    if companyInfoJson is None or len(companyInfoJson) == 0:
        return json.dumps({'Message': 'Nada foi encontrado aqui!'}), 400, {'content-type': 'application/json'}

    result = [dict({"value": stock['normalizedName'], "text": stock['name']})
              for stock in companyInfoJson]

    return json.dumps(result), 200, {'content-type': 'application/json'}


@bpDre.route('/dre/data', methods=['POST'])
def data():
    form = request.form
    # and form.validate():
    if form.get('tickerSelect') != "" and request.method == 'POST':
        respJson = json.loads(dreApi(form.get('tickerSelect'))[0])
        return render_template('dre.jinja', form=form, stocks=respJson,
                               colnames=(respJson[0]).keys())
        # if(respJson[1] == 400):
        #    return render_template('dre.jinja', errorMsg=respJson[0])
    return render_template('dre.jinja', form=request.form)


@bpDre.route('/api/dre/<companyId>')
def dreApi(companyId):
    current_app.logger.info("### DRE API ###")

    yearNow = datetime.datetime.now().year
    callUrl = "https://statusinvest.com.br/acao/getdre?"
    callUrl += "companyName=" + companyId
    callUrl += "&type=0&range.min=2000"
    callUrl += "&range.max=" + str(yearNow)

    resp = requests.get(callUrl)
    dreDataJson = json.loads(resp.text)
    grid = dreDataJson['grid']

    locale.setlocale(locale.LC_MONETARY, '')

    ''' iniciando com a coluna dos anos, nos dados retornados pelo
        statusinvest, eles tem um lista propria, separada do resto dos dados
    '''
    dreDataJson['years'].sort(reverse=True)
    ''' copiando os anos ordenados do maior para o menor, o formato é uma lista
        de dict, porque é de facil aceitação pela biblioteca json
    '''
    finalData = [dict({'year': [year, "#000000"]})
                 for year in dreDataJson['years']]
    # inserindo TTM no inicio da lista
    finalData.insert(0, dict({'year': ['TTM', "#000000"]}))

    ignoreKeys = ['Custos - (R$)', 'Lucro Bruto - (R$)', 'Despesas Receitas Operacionais - (R$)',
                  'Amortização Depreciação', 'EBIT - (R$)', 'Resultado não operacional - (R$)',
                  'Impostos - (R$)', 'Lucro atribuído a Controladora', 'Lucro atribuído a Não Controladores',
                  'Dívida Bruta - (R$)', 'ROIC - (%)', 'Margem Bruta - (%)', 'Margem Ebitda - (%)']

    callUrl = "https://statusinvest.com.br/acao/getbsactivepassivechart?"
    callUrl += "companyName=" + companyId
    callUrl += "&type=2"

    respPassive = requests.get(callUrl)
    passiveDataJson = json.loads(respPassive.text)

    for idxLine, line in enumerate(passiveDataJson):
        valueTmp = (str(line['patrimonioLiquido']))[:-6]
        value = ('%.2f' % float(valueTmp[:-2] + '.' + valueTmp[2:])) + "M"
        color = "#cc0000" if value.startswith("-") else "#2b1d0e"
        if idxLine == 0:
            finalData[0].update(
                {'Patrimônio Líquido': [value, color]})
        for idx, data in enumerate(finalData):
            if (data['year'])[0] == line['year']:
                finalData[idx].update(
                    {'Patrimônio Líquido': [value, color]})

    ''' vamos para a lista contendo os dados, será necessario
        transpor os dados de colunas para linhas
    '''
    for idx, content in enumerate(grid):
        # print(idx, content['isHeader'])
        ''' a primeira entrada da grid é o header, não precisamos dela,
            pois iremos pega-lo mais a frente
        '''
        if content['isHeader']:
            continue
        columns = content['columns']
        colName = ''
        countDictItems = 0

        for idxCol in range(0, len(columns)-1, 1):
            col = columns[idxCol]
            # indice 0 é o nome da coluna
            if idxCol == 0:
                # current_app.logger.debug(f'{idxCol} - {columns[idxCol]}')
                colName = col['value'].replace("/", "\x20")
                continue
            ''' indices com nome de coluna = DATA são os valores anuais, não
                temos interesse em percentuais de crescimento ano a ano
            '''
            if 'DATA' in col['name'] and colName not in ignoreKeys:
                # current_app.logger.debug(
                #    f'{idxCol} - {countDictItems} - {finalData[countDictItems]}')
                value = (col['value']).replace("\x20", "")
                if value == "-":
                    color = "#000000"
                elif "(%)" in colName:
                    color = "#cc0000" if value.startswith("-") else "#505050"
                elif "CAPEX - (R$)" in colName:
                    color = "#000000"
                elif "Dívida Líquida - (R$)" in colName:
                    color = "#228b22" if value.startswith("-") else "#cc0000"
                elif "Dívida Líquida Ebitda" in colName:
                    valueColor = float(value.replace(",", "."))
                    color = "#228b22" if valueColor < 2 else \
                        "#cc0000" if valueColor > 3 else "#d4af37"
                else:
                    color = "#cc0000" if value.startswith("-") else "#228b22"

                finalData[countDictItems].update({colName: [value, color]})
                countDictItems += 1

        # stock['price'] = locale.currency(stock['price'])
        # stock['vpa'] = '%.2f' % stock['vpa']
        # stock['lpa'] = '%.2f' % stock['lpa']
        # stock['val_Intrinseco'] = locale.currency(stock['val_Intrinseco'])

    ignoreCashKeys = ['Saldo Final de Caixa e Equivalentes - (R$)', 'Saldo Inicial de Caixa e Equivalentes - (R$)',
                      'Aumento de Caixa e Equivalentes - (R$)', 'Variação Cambial de Caixa e Equivalentes - (R$)',
                      'Variações nos Ativos e Passivos - (R$)', 'Depreciação e Amortização - (R$)',
                      'Lucro Líquido - (R$)', 'Equivalência Patrimonial - (R$)', 'Caixa Líquido Atividades de Investimento - (R$)']

    callUrl = "https://statusinvest.com.br/acao/getfluxocaixa?"
    callUrl += "companyName=" + companyId
    callUrl += "&type=0"

    respCash = requests.get(callUrl)
    cashDataJson = json.loads(respCash.text)

    for idx, content in enumerate(cashDataJson):
        if content['isHeader']:
            continue
        columnsList = content['columns']
        colName = ''
        countDictItems = 0
        for idxCol, col in enumerate(columnsList):
            if idxCol == 0:
                colName = col['value'].replace("/", "\x20")
                continue
            if 'DATA' in col['name'] and colName not in ignoreCashKeys:
                # current_app.logger.debug(
                #    f'{idxCol} - {countDictItems} - {finalData[countDictItems]}')
                value = (col['value']).replace("\x20", "")
                color = "#000000"
                if countDictItems == 0:
                    finalData[0].update({colName: [value, color]})
                if countDictItems+1 < len(finalData):
                    finalData[countDictItems +
                              1].update({colName: [value, color]})
                    countDictItems += 1

    callUrl = "https://statusinvest.com.br/acao/payoutresult?"
    callUrl += "companyName=" + companyId
    callUrl += "&type=2"

    respPayout = requests.get(callUrl)
    payoutDataJson = json.loads(respPayout.text)

    percentualData = ((payoutDataJson['chart'])['series'])['percentual']
    proventosData = ((payoutDataJson['chart'])['series'])['proventos']

    percentualData.reverse()
    proventosData.reverse()

    for idxPercent in range(0, len(percentualData)-1, 1):
        valuePerc = (percentualData[idxPercent])["value_F"]
        valueProv = (proventosData[idxPercent])["valueSmall_F"]
        valuePercColor = float(valuePerc.replace(",", ".").replace("%", ""))
        colorPerc = "#cc0000" if valuePercColor < 30 else \
            "#228b22" if valuePercColor > 70 else "#d4af37"
        if idxPercent == 0:
            finalData[0].update(
                {'Proventos': [valueProv, "#d4af37"]})
            finalData[0].update(
                {'Payout': [valuePerc, colorPerc]})
        if idxPercent+1 < len(finalData):
            finalData[idxPercent+1].update(
                {'Proventos': [valueProv, "#d4af37"]})
            finalData[idxPercent+1].update(
                {'Payout': [valuePerc, colorPerc]})

    # print(years)
    # print(finalData)

    return json.dumps(finalData), 200, {'content-type': 'application/json'}
